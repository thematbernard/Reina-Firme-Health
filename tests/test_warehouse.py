"""Layer 1: warehouse integrity + MCP guardrails.

Fast, deterministic, no LLM. Everything here answers "is the thing the agent
reads actually true?". Agent-level evals (does Claude reach the right answer)
live in evals/ and are a separate, slower suite.

Run:  make test
"""

import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "warehouse.duckdb"
JOINS = json.loads((ROOT / "semantic" / "joins.json").read_text())["joins"]

sys.path.insert(0, str(ROOT / "mcp_server"))

pytestmark = pytest.mark.skipif(
    not DB.exists(), reason="warehouse.duckdb not built — run `make marts`"
)


@pytest.fixture(scope="session")
def con():
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


def jid(j):
    return f"{j['left']}.{j['left_col']}->{j['right'].split('.')[-1]}"


# --- the semantic layer must match the warehouse ------------------------------

def test_schema_doc_is_current():
    """semantic/schema.md is generated; fail if someone changed the warehouse
    without regenerating. This is the test that would have caught the original
    ops_facilities.name / ops_appointments.patient_id drift."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "pipeline" / "05_gen_schema_doc.py"), "--check"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("j", JOINS, ids=jid)
def test_join_path_has_no_orphans(con, j):
    """Every documented join path resolves. Measured 0 orphans across all 24
    paths at build time, so any orphan is a real regression."""
    lt, lc, rt, rc = j["left"], j["left_col"], j["right"], j["right_col"]
    orphans = con.execute(
        f'SELECT count(*) FROM {lt} WHERE "{lc}" IS NOT NULL '
        f'AND "{lc}" NOT IN (SELECT "{rc}" FROM {rt})'
    ).fetchone()[0]
    assert orphans == 0


@pytest.mark.parametrize("j", JOINS, ids=jid)
def test_join_null_rate_as_documented(con, j):
    """A FK that starts or stops being null changes what a LEFT vs INNER join
    means. Declared nullable_pct (default 0) must hold within 2pp."""
    lt, lc = j["left"], j["left_col"]
    total, nonnull = con.execute(
        f'SELECT count(*), count("{lc}") FROM {lt}'
    ).fetchone()
    actual = 100.0 * (total - nonnull) / total
    assert actual == pytest.approx(j.get("nullable_pct", 0.0), abs=2.0)


def test_all_tables_non_empty(con):
    """Catches a silently truncated or failed parquet extract."""
    tables = con.execute(
        "SELECT table_schema || '.' || table_name FROM information_schema.tables "
        "WHERE table_schema IN ('raw','marts')"
    ).fetchall()
    assert len(tables) == 24, f"expected 24 tables, found {len(tables)}"
    empty = [t for (t,) in tables if con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] == 0]
    assert not empty


# --- identity crosswalk invariants -------------------------------------------

def test_xwalk_is_one_to_one(con):
    """A member must not be claimed by two patients, or vice versa — otherwise
    any join through the crosswalk fans out and double-counts claims."""
    dup_p, dup_m = con.execute(
        """SELECT (SELECT count(*) FROM (SELECT patient_id FROM marts.identity_xwalk
                    GROUP BY 1 HAVING count(*) > 1)),
                  (SELECT count(*) FROM (SELECT member_id FROM marts.identity_xwalk
                    GROUP BY 1 HAVING count(*) > 1))"""
    ).fetchone()
    assert (dup_p, dup_m) == (0, 0)


def test_xwalk_coverage_in_band(con):
    """Documented as 87% of patients linked. A large move means the matcher
    or the source data changed and the dictionary claim is now a lie."""
    pct = con.execute(
        "SELECT 100.0 * (SELECT count(*) FROM marts.identity_xwalk) "
        "/ (SELECT count(*) FROM raw.ehr_patients)"
    ).fetchone()[0]
    assert 85.0 <= pct <= 89.0, f"coverage {pct:.1f}% outside documented 87%"


def test_xwalk_confidence_matches_method(con):
    """exact/exact_tiebreak must be confidence 1.0; fuzzy must clear the 0.92
    Jaro-Winkler threshold the SQL claims to enforce."""
    rows = dict(
        (m, (lo, hi)) for m, lo, hi in con.execute(
            "SELECT match_method, min(match_confidence), max(match_confidence) "
            "FROM marts.identity_xwalk GROUP BY 1"
        ).fetchall()
    )
    assert set(rows) == {"exact", "exact_tiebreak", "fuzzy"}
    assert rows["exact"] == (1.0, 1.0)
    assert rows["exact_tiebreak"] == (1.0, 1.0)
    assert rows["fuzzy"][0] >= 0.92


# --- documented numbers must stay true ---------------------------------------

def test_time_windows_as_documented(con):
    """Dictionary rule R2. Comparing a 3-year table to a 1-year one without
    windowing is the single easiest way to get a 3x-wrong answer."""
    cases = [
        ("raw.payer_claims", "service_date", "2023-06-01", "2026-05-31"),
        ("raw.ehr_encounters", "admission_dt", "2023-06-01", "2026-05-31"),
        ("raw.ops_appointments", "scheduled_dt_local", "2025-06-01", "2026-05-31"),
        ("raw.ops_or_schedule", "scheduled_start_dt_local", "2025-06-01", "2026-05-30"),
    ]
    for table, col, lo, hi in cases:
        a, b = con.execute(f"SELECT min({col})::date, max({col})::date FROM {table}").fetchone()
        assert str(a) == lo and str(b) == hi, f"{table}.{col}: {a}..{b} != {lo}..{hi}"


def test_owned_network_shape_as_documented(con):
    """Dictionary claims 84 owned facilities: 8 hospitals, 64 clinics, 12 UC."""
    got = dict(con.execute(
        "SELECT facility_type, count(*) FROM raw.ops_facilities "
        "WHERE ownership='owned' GROUP BY 1"
    ).fetchall())
    assert got == {"hospital": 8, "clinic": 64, "urgent_care": 12}


def test_caveat_c1_random_provider_assignment_still_holds(con):
    """Caveat C1: ops_appointments.provider_id is randomly assigned (~1.2% of
    appointments land at the provider's own facility, i.e. chance for 84
    sites). If this ever rises materially, C1 is stale and provider-normalized
    utilization becomes valid again — so the dictionary must be updated."""
    pct = con.execute(
        "SELECT 100.0 * avg(CASE WHEN p.primary_facility_id = a.facility_id THEN 1 ELSE 0 END) "
        "FROM raw.ops_appointments a JOIN raw.ops_providers p USING (provider_id)"
    ).fetchone()[0]
    assert pct < 5.0, f"provider/facility agreement now {pct:.1f}% — revisit caveat C1"


def test_caveat_c5_owned_clinic_counts(con):
    """Caveat C5: Sacramento 4 owned clinics, Atlanta 8 — the denominators the
    Sacramento-vs-Atlanta question depends on."""
    got = dict(con.execute(
        "SELECT city, count(*) FROM raw.ops_facilities "
        "WHERE ownership='owned' AND facility_type='clinic' "
        "AND city IN ('Sacramento','Atlanta') GROUP BY 1"
    ).fetchall())
    assert got == {"Sacramento": 4, "Atlanta": 8}


# --- MCP server guardrails ---------------------------------------------------

@pytest.mark.parametrize("sql", [
    "DROP TABLE raw.payer_claims",
    "DELETE FROM marts.identity_xwalk",
    "INSERT INTO marts.identity_xwalk VALUES ('a','b','exact',1.0)",
    "UPDATE marts.identity_xwalk SET member_id = 'x'",
    "CREATE TABLE evil AS SELECT 1",
    "ATTACH 'other.duckdb' AS other",
    "COPY raw.payer_members TO '/tmp/exfil.csv'",
    "SELECT 1; DROP TABLE raw.payer_claims",
])
def test_run_query_rejects_non_read_queries(sql):
    import server
    assert server.run_query(sql).startswith("error:")


def test_write_blocked_even_past_the_regex():
    """Defense in depth: a statement starting with WITH clears the allowlist
    regex, so the read_only connection must be what actually stops it."""
    import server
    out = server.run_query(
        "WITH x AS (SELECT 1) DELETE FROM marts.identity_xwalk WHERE patient_id IN (SELECT 1 FROM x)"
    )
    assert out.startswith("error:")


def test_run_query_enforces_row_cap():
    import server
    out = server.run_query("SELECT member_id FROM raw.payer_members")
    assert len(out.splitlines()) <= server.MAX_ROWS + 2
    assert "truncated" in out


def test_run_query_returns_rows():
    import server
    out = server.run_query("SELECT count(*) AS n FROM raw.ops_facilities")
    assert out.splitlines()[1].strip() == "284"


def test_describe_table_rejects_injection():
    import server
    assert server.describe_table("raw.x; DROP TABLE y").startswith("error:")


def test_dictionary_defers_column_facts_to_generated_schema():
    """Regression guard on the root cause: column facts belong in the generated
    schema.md, never in the hand-written dictionary. Structural check, not a
    string blacklist — the dictionary legitimately *names* the stale columns as
    a cautionary example."""
    text = (ROOT / "semantic" / "dictionary.md").read_text()
    assert "schema.md" in text, "dictionary must point at the generated schema"
    assert "| column |" not in text, "column tables belong in schema.md"
    # no line may enumerate a long comma-separated column list (the old pattern)
    for i, line in enumerate(text.splitlines(), 1):
        assert line.count(",") < 5, f"dictionary.md:{i} looks like a column list"


# --- analysis findings must stay reproducible --------------------------------
# These pin the conclusions in analysis/02_sacramento_vs_atlanta.md. If the
# warehouse is rebuilt and these move, the analysis prose is stale.

def test_clinic_throughput_is_uniform(con):
    """Caveat C2, and the whole basis of the Sacramento conclusion: no two of
    the 64 owned clinics differ by more than ~3% in completed appointments, so
    a 40% utilization gap is not constructible from throughput."""
    n, cv, ratio = con.execute(
        """WITH v AS (
             SELECT count(*) FILTER (WHERE a.status='completed') c
             FROM raw.ops_appointments a JOIN raw.ops_facilities f USING (facility_id)
             WHERE f.ownership='owned' AND f.facility_type='clinic'
             GROUP BY f.facility_id)
           SELECT count(*), 100.0*stddev(c)/avg(c), max(c)*1.0/min(c) FROM v"""
    ).fetchone()
    assert n == 64
    assert cv < 2.0, f"clinic throughput CV now {cv:.2f}% — caveat C2 may be stale"
    assert ratio < 1.10, f"max/min now {ratio:.3f} — a real utilization gap may exist"


def test_size_matched_pair_has_no_gap(con):
    """The size-matched Sacramento/Atlanta clinics differ by <2% in completed
    appointments — the direct refutation of the 40% premise."""
    rows = dict(con.execute(
        """SELECT facility_id, count(*) FILTER (WHERE status='completed')
           FROM raw.ops_appointments
           WHERE facility_id IN ('FAC-00015','FAC-00052') GROUP BY 1"""
    ).fetchall())
    sac, atl = rows["FAC-00015"], rows["FAC-00052"]
    assert abs(sac - atl) / atl < 0.02, f"Sacramento {sac} vs Atlanta {atl}"


def test_sacramento_has_no_owned_acute_care(con):
    """The real finding: Sacramento has clinics but no owned hospital or
    urgent care, which is what drives its out-of-market leakage."""
    got = dict(con.execute(
        "SELECT facility_type, count(*) FROM raw.ops_facilities "
        "WHERE ownership='owned' AND city='Sacramento' GROUP BY 1"
    ).fetchall())
    assert got.get("hospital", 0) == 0 and got.get("urgent_care", 0) == 0
    assert got["clinic"] == 4


def test_sacramento_out_of_market_leakage(con):
    """Sacramento sends ~83% of allowed dollars out of market vs Atlanta's ~31%."""
    rows = dict(con.execute(
        """WITH mm AS (SELECT member_id, city mc FROM raw.payer_members
                       WHERE city IN ('Sacramento','Atlanta'))
           SELECT mm.mc,
                  100.0*sum(CASE WHEN f.city <> mm.mc THEN c.allowed_amount ELSE 0 END)
                        / sum(c.allowed_amount)
           FROM raw.payer_claims c JOIN mm USING (member_id)
           JOIN raw.ops_facilities f ON f.facility_id = c.facility_id
           GROUP BY 1"""
    ).fetchall())
    assert rows["Sacramento"] == pytest.approx(82.9, abs=1.0)
    assert rows["Atlanta"] == pytest.approx(31.0, abs=1.0)

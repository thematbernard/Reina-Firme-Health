"""Mart integrity.

The point of a mart is that the agent stops hand-assembling joins, which means
the mart is now the only thing standing between it and a wrong answer. So the
load-bearing test here is not "does the mart have rows" — it is "does the mart
still agree with raw". A mart that silently drifts from source is worse than no
mart, because nobody re-derives the number to catch it.
"""

import duckdb
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "warehouse.duckdb"

pytestmark = pytest.mark.skipif(not DB.exists(), reason="run `make marts`")

WIN = "DATE '2025-06-01' AND DATE '2026-06-01'"


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


# --- grain --------------------------------------------------------------------

def test_facility_metrics_grain(con):
    """One row per facility, all 284, no duplicates, no null keys."""
    n, distinct, nulls = con.execute(
        """SELECT count(*), count(DISTINCT facility_id),
                  count(*) FILTER (WHERE facility_id IS NULL
                                      OR ownership IS NULL
                                      OR facility_type IS NULL)
           FROM marts.facility_metrics"""
    ).fetchone()
    assert n == distinct == 284
    assert nulls == 0


def test_market_summary_grain(con):
    n, distinct = con.execute(
        "SELECT count(*), count(DISTINCT city) FROM marts.market_summary"
    ).fetchone()
    assert n == distinct == 42


# --- the load-bearing tests: mart must agree with raw -------------------------

def test_facility_metrics_appointments_agree_with_raw(con):
    """Windowed appointment counts must match a direct raw query exactly."""
    mart, raw = con.execute(
        f"""SELECT (SELECT sum(appts_completed) FROM marts.facility_metrics),
                   (SELECT count(*) FROM raw.ops_appointments
                    WHERE status = 'completed'
                      AND scheduled_dt_local >= {WIN.split(' AND ')[0]}
                      AND scheduled_dt_local <  {WIN.split(' AND ')[1]})"""
    ).fetchone()
    assert mart == raw, f"mart {mart:,} != raw {raw:,}"


def test_facility_metrics_claims_agree_with_raw(con):
    """Windowed claims and dollars must reconcile to raw.payer_claims."""
    m_claims, m_allowed, r_claims, r_allowed = con.execute(
        f"""SELECT (SELECT sum(claims) FROM marts.facility_metrics),
                   (SELECT sum(allowed_amount) FROM marts.facility_metrics),
                   (SELECT count(*) FROM raw.payer_claims
                    WHERE service_date >= {WIN.split(' AND ')[0]}
                      AND service_date <  {WIN.split(' AND ')[1]}),
                   (SELECT sum(allowed_amount) FROM raw.payer_claims
                    WHERE service_date >= {WIN.split(' AND ')[0]}
                      AND service_date <  {WIN.split(' AND ')[1]})"""
    ).fetchone()
    assert m_claims == r_claims
    assert float(m_allowed) == pytest.approx(float(r_allowed), rel=1e-9)


def test_market_summary_members_agree_with_raw(con):
    mart, raw = con.execute(
        """SELECT (SELECT sum(members_total) FROM marts.market_summary),
                  (SELECT count(*) FROM raw.payer_members)"""
    ).fetchone()
    assert mart == raw


def test_market_summary_facility_counts_agree(con):
    """owned_* columns must reconcile to facility_metrics, or market ranking
    silently uses the wrong denominator (the C5 failure, one level up)."""
    mart, fm = con.execute(
        """SELECT (SELECT sum(owned_facilities) FROM marts.market_summary),
                  (SELECT count(*) FROM marts.facility_metrics WHERE ownership = 'owned')"""
    ).fetchone()
    assert mart == fm == 84


# --- caveats are now structurally enforced, not documented -------------------

def test_c1_is_retired_by_construction(con):
    """providers_based must come from ops_providers.primary_facility_id. If it
    were sourced from ops_appointments.provider_id every facility would show
    ~5,597. Assert nothing is even close."""
    lo, hi = con.execute(
        "SELECT min(providers_based), max(providers_based) FROM marts.facility_metrics"
    ).fetchone()
    assert 20 <= lo and hi < 200, f"providers_based spans {lo}-{hi}"
    total, roster = con.execute(
        """SELECT (SELECT sum(providers_based) FROM marts.facility_metrics),
                  (SELECT count(*) FROM raw.ops_providers)"""
    ).fetchone()
    assert total == roster == 14000, "every provider assigned exactly once"


def test_or_utilization_uses_operating_days(con):
    """The corrected denominator puts every hospital in the low 50s. A 365-day
    denominator would land them near 40 — that regression must fail here."""
    rows = con.execute(
        """SELECT or_utilization_pct FROM marts.facility_metrics
           WHERE or_utilization_pct IS NOT NULL"""
    ).fetchall()
    vals = [r[0] for r in rows]
    assert len(vals) == 8
    assert all(50 < v < 60 for v in vals), vals
    assert 270 <= con.execute(
        "SELECT min(or_operating_days) FROM marts.facility_metrics "
        "WHERE or_operating_days IS NOT NULL"
    ).fetchone()[0] <= 300


def test_c6_uniformity_is_visible_not_hidden(con):
    """pct_allowed_owned is carried so its uselessness is observable. If the
    spread ever widens, C6 is stale and market ranking should reconsider it."""
    spread = con.execute(
        """SELECT max(pct_allowed_owned) - min(pct_allowed_owned)
           FROM marts.market_summary WHERE members_active > 20000"""
    ).fetchone()[0]
    assert spread < 3.0, f"owned-share spread now {spread:.1f}pp — revisit C6"


# --- the marts must still answer the two strategy questions ------------------

def test_q2_answerable_in_one_query(con):
    """The Sacramento/Atlanta comparison, with no joins and no CTEs."""
    rows = dict(con.execute(
        """SELECT city, avg(appts_completed) FROM marts.facility_metrics
           WHERE ownership = 'owned' AND facility_type = 'clinic'
             AND city IN ('Sacramento', 'Atlanta') GROUP BY 1"""
    ).fetchall())
    assert abs(rows["Sacramento"] - rows["Atlanta"]) / rows["Atlanta"] < 0.02


def test_q1_answerable_in_one_query(con):
    """Sacramento must rank worst on acute access among real markets, with no
    owned hospital or urgent care — the whole Q1 recommendation."""
    top = con.execute(
        """SELECT city, owned_hospitals, owned_urgent_care, median_miles_to_acute
           FROM marts.market_summary WHERE members_active > 20000
           ORDER BY median_miles_to_acute DESC LIMIT 1"""
    ).fetchone()
    city, hosp, uc, miles = top
    assert city == "Sacramento"
    assert hosp == 0 and uc == 0
    assert miles == pytest.approx(75.5, abs=2.0)


def test_recapture_dollars_do_not_by_themselves_pick_sacramento(con):
    """An honest guard on the Q1 narrative: ranking markets purely by recapture
    dollars favours the big markets that ALREADY have a hospital. The case for
    Sacramento rests on access. If someone later claims recapture alone selects
    Sacramento, this fails."""
    rows = dict(con.execute(
        """SELECT city, recapture_plan_paid_musd FROM marts.market_summary
           WHERE members_active > 20000"""
    ).fetchall())
    assert rows["Atlanta"] > rows["Sacramento"]

    corridor = sum(rows[c] for c in ("Sacramento", "Stockton", "Modesto"))
    assert corridor == pytest.approx(33.2, abs=1.5), corridor

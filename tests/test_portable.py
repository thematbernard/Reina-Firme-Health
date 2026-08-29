"""The portable, PII-free artifact and the marts-only serving mode.

Point of the artifact: today the repo needs Redshift credentials and a ~1 hour
extract before anyone can try the MCP server. A 7 MB marts-only file removes
that barrier. The risk it introduces is exporting data that should not travel,
so the PII guard is the load-bearing test here — negative-controlled, because a
guard that has never been seen to fire is not a guard.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).parent.parent
EXPORTER = ROOT / "pipeline" / "06_export_portable.py"
SERVER = ROOT / "mcp_server" / "server.py"
FULL = ROOT / "data" / "warehouse.duckdb"
PORTABLE = ROOT / "data" / "portable" / "reina_marts.duckdb"

pytestmark = pytest.mark.skipif(not FULL.exists(), reason="run `make marts`")


def load_exporter():
    spec = importlib.util.spec_from_file_location("exporter", EXPORTER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# --- the PII guard ------------------------------------------------------------

def test_pii_guard_passes_on_the_real_marts():
    exp = load_exporter()
    con = duckdb.connect(str(FULL), read_only=True)
    try:
        assert exp.pii_columns(con) == []
    finally:
        con.close()


def test_pii_guard_fires_on_an_injected_pii_column(tmp_path):
    """Negative control. Build a marts table carrying names and DOB and assert
    the guard catches it — otherwise the export is unprotected."""
    exp = load_exporter()
    db = tmp_path / "leaky.duckdb"
    con = duckdb.connect(str(db))
    try:
        con.execute("CREATE SCHEMA marts")
        con.execute(
            "CREATE TABLE marts.leaky AS SELECT 'x' AS first_name, 'y' AS last_name, "
            "DATE '1980-01-01' AS dob, 'a@b.c' AS email, '123 Main' AS address_line1"
        )
        found = {c for _, c in exp.pii_columns(con)}
        assert {"first_name", "last_name", "dob", "email", "address_line1"} <= found
    finally:
        con.close()


def test_exporter_refuses_end_to_end_when_pii_present(tmp_path, monkeypatch):
    """The guard must abort the export, not merely report."""
    exp = load_exporter()
    leaky = tmp_path / "src.duckdb"
    con = duckdb.connect(str(leaky))
    con.execute("CREATE SCHEMA marts")
    con.execute("CREATE TABLE marts.people AS SELECT 'a' AS first_name")
    con.close()

    monkeypatch.setattr(exp, "SRC", leaky)
    monkeypatch.setattr(exp, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(exp, "OUT", tmp_path / "out" / "x.duckdb")
    with pytest.raises(SystemExit) as e:
        exp.main()
    assert "REFUSING TO EXPORT" in str(e.value)
    assert not (tmp_path / "out" / "x.duckdb").exists(), "wrote a leaky artifact"


def test_facility_name_is_allowlisted_as_non_personal(tmp_path):
    """A business name is not a personal name; without the allowlist the guard
    would block every legitimate export."""
    exp = load_exporter()
    assert "facility_name" in exp.PII_ALLOWLIST


# --- the artifact itself ------------------------------------------------------

@pytest.mark.skipif(not PORTABLE.exists(), reason="run `make portable`")
def test_artifact_is_self_contained_and_small():
    """No external parquet dependency: it must carry TABLES, not views over
    absolute local paths, or it breaks the moment it leaves this machine."""
    assert PORTABLE.stat().st_size < 100_000_000, "too large for a git artifact"
    con = duckdb.connect(str(PORTABLE), read_only=True)
    try:
        views = con.execute("SELECT count(*) FROM duckdb_views() "
                            "WHERE schema_name IN ('raw','marts')").fetchone()[0]
        assert views == 0, "artifact contains views — not portable"
        tables = {t for (t,) in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE schema_name='marts'").fetchall()}
        assert {"facility_metrics", "market_summary", "identity_xwalk"} <= tables
    finally:
        con.close()


@pytest.mark.skipif(not PORTABLE.exists(), reason="run `make portable`")
def test_both_strategy_questions_answerable_from_the_artifact_alone():
    """The whole justification: a reviewer with no source access still gets the
    answers."""
    con = duckdb.connect(str(PORTABLE), read_only=True)
    try:
        q1 = con.execute(
            """SELECT city, owned_hospitals, median_miles_to_acute
               FROM marts.market_summary WHERE members_active > 20000
               ORDER BY median_miles_to_acute DESC LIMIT 1"""
        ).fetchone()
        assert q1[0] == "Sacramento" and q1[1] == 0

        rows = dict(con.execute(
            """SELECT city, avg(appts_completed) FROM marts.facility_metrics
               WHERE ownership='owned' AND facility_type='clinic'
                 AND city IN ('Sacramento','Atlanta') GROUP BY 1"""
        ).fetchall())
        assert abs(rows["Sacramento"] - rows["Atlanta"]) / rows["Atlanta"] < 0.02
    finally:
        con.close()


# --- serving mode is derived from the data, not the path ---------------------

def test_mode_detected_from_data_not_filename(monkeypatch):
    """A REINA_DB override pointing at a marts-only file must still report
    marts-only, or the agent hunts for raw.* tables that do not exist."""
    spec = importlib.util.spec_from_file_location("srv_mode", SERVER)
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    assert srv.detect_mode(FULL) == "full"
    if PORTABLE.exists():
        assert srv.detect_mode(PORTABLE) == "portable"


@pytest.mark.skipif(not PORTABLE.exists(), reason="run `make portable`")
def test_marts_only_server_warns_over_stdio():
    """End-to-end: a client talking to a marts-only deployment must be told, in
    both the instructions and the dictionary, that raw.* is unavailable."""
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)], cwd=str(ROOT),
        env={**os.environ, "REINA_DB": str(PORTABLE)},
    )

    async def main():
        with anyio.fail_after(60):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as s:
                    await s.initialize()
                    dictionary = await s.call_tool("get_data_dictionary", {})
                    tables = await s.call_tool("list_tables", {})
                    return (s.instructions,
                            "\n".join(c.text for c in dictionary.content),
                            "\n".join(c.text for c in tables.content))

    instructions, dictionary, tables = anyio.run(main)
    assert "marts-only" in instructions
    assert "MARTS-ONLY" in dictionary[:600]
    assert "raw." not in tables
    assert "marts.market_summary" in tables


def test_transport_flag_exists():
    """Hosting must be a flag, not a code change."""
    out = subprocess.run(
        [sys.executable, str(SERVER), "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert "--transport" in out.stdout
    assert "streamable-http" in out.stdout

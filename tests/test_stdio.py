"""Exercise the MCP server over its real stdio transport.

Every other test in this suite imports mcp_server/server.py and calls the tool
functions directly. That leaves the transport itself uncovered: if tool
registration, JSON-RPC framing, schema serialization or server startup were
broken, all of those tests would still pass and a live client would still fail.

This spawns the server as a subprocess exactly as Claude Desktop does, performs
the initialize handshake, and round-trips every tool through the protocol.

No credential and no network needed. Async bodies are driven with anyio.run so
no pytest async plugin is required.
"""

import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).parent.parent
SERVER = ROOT / "mcp_server" / "server.py"
DB = ROOT / "data" / "warehouse.duckdb"
TIMEOUT = 60

pytestmark = pytest.mark.skipif(not DB.exists(), reason="run `make marts`")

PARAMS = StdioServerParameters(
    command=sys.executable, args=[str(SERVER)], cwd=str(ROOT)
)


def run(coro_fn):
    """Drive one async client session to completion, with a hard timeout so a
    hung server fails the test instead of hanging CI."""
    async def main():
        with anyio.fail_after(TIMEOUT):
            async with stdio_client(PARAMS) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await coro_fn(session)
    return anyio.run(main)


def text_of(result) -> str:
    """Concatenate the text content blocks of a CallToolResult."""
    return "\n".join(
        c.text for c in result.content if getattr(c, "type", None) == "text"
    )


# --- the transport comes up at all -------------------------------------------

def test_server_starts_and_completes_handshake():
    """If server.py has an import error, a bad DB path, or fails to register
    tools, this is where it surfaces — before a live demo."""
    async def body(session):
        return session.protocol_version, len((await session.list_tools()).tools)

    protocol, n_tools = run(body)
    assert protocol, "no protocol version negotiated"
    assert n_tools == 5


def test_server_info_and_instructions_transport():
    async def body(session):
        return session.server_info, session.instructions

    info, instructions = run(body)
    assert info.name == "reina-firme-analytics"
    # the instructions string steers the client's model; it must survive transport
    assert instructions and "get_data_dictionary" in instructions
    assert "Do not guess column names" in instructions


# --- tool registration and schema serialization ------------------------------

def test_tool_descriptions_round_trip_unmangled():
    """Descriptions reach the client intact (not truncated or re-encoded).

    NOTE what this canNOT do: expected and actual both derive from the same
    server.py, so it cannot detect that a *separately running* server is stale.
    A test cannot reach into another process. Staleness is covered two other
    ways: the golden file below (drift must be a deliberate, reviewed edit) and
    the server's own build fingerprint (visible to a live client)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("srv", SERVER)
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)

    tools = {t.name: t for t in run(lambda s: s.list_tools()).tools}
    assert set(tools) == {
        "get_data_dictionary", "list_tables", "describe_table", "run_query",
        "query_source",
    }
    for name, tool in tools.items():
        expected = " ".join(getattr(srv, name).__doc__.split())
        assert " ".join((tool.description or "").split()) == expected, (
            f"{name}: transported description does not match server.py docstring"
        )

    # parameter schemas must survive serialization
    assert "table" in tools["describe_table"].input_schema["properties"]
    assert "sql" in tools["run_query"].input_schema["properties"]
    assert "sql" in tools["query_source"].input_schema["properties"]
    assert tools["list_tables"].input_schema.get("properties", {}) == {}


# --- every tool round-trips --------------------------------------------------

def test_list_tables_over_stdio():
    out = text_of(run(lambda s: s.call_tool("list_tables", {})))
    for expected in ("marts.facility_metrics", "marts.market_summary",
                     "marts.identity_xwalk", "raw.payer_claims"):
        assert expected in out


def test_list_tables_marks_views_instead_of_blank():
    """A blank count reads as "zero rows" to an agent. raw.* are views over
    parquet with no stored size, so they must say so explicitly."""
    rows = dict(
        line.split("\t", 1)
        for line in text_of(run(lambda s: s.call_tool("list_tables", {}))).splitlines()[1:]
    )
    assert rows["raw.payer_claims"] == "view"
    assert rows["marts.facility_metrics"].isdigit()
    assert "" not in rows.values()


def test_describe_table_over_stdio():
    out = text_of(run(lambda s: s.call_tool(
        "describe_table", {"table": "raw.ops_facilities"})))
    assert "facility_name" in out and "ownership" in out


def test_run_query_over_stdio():
    out = text_of(run(lambda s: s.call_tool(
        "run_query", {"sql": "SELECT count(*) AS n FROM raw.ops_facilities"})))
    assert out.splitlines()[1].strip() == "284"


def test_get_data_dictionary_carries_the_generated_schema():
    """Regression guard on the stale-server problem: the current server appends
    the GENERATED schema reference. A server predating that change returns only
    the hand-written half, and the agent goes back to guessing column names."""
    out = text_of(run(lambda s: s.call_tool("get_data_dictionary", {})))
    assert "Schema Reference (GENERATED)" in out
    assert "facility_name" in out          # generated column list present
    assert "marts.facility_metrics" in out  # marts documented
    assert len(out) > 15000


# --- error paths must serialize as results, not blow up the transport --------

def test_guardrail_error_returns_as_content_not_a_crash():
    """A rejected write must come back as a normal tool result. If it raised
    through the transport instead, the client session would break mid-demo."""
    out = text_of(run(lambda s: s.call_tool(
        "run_query", {"sql": "DROP TABLE raw.payer_claims"})))
    assert out.startswith("error:")
    assert "only SELECT" in out


def test_sql_error_returns_as_content():
    out = text_of(run(lambda s: s.call_tool(
        "run_query", {"sql": "SELECT nope FROM raw.ops_facilities"})))
    assert out.startswith("error:")


def test_large_result_survives_serialization():
    """The 500-row cap produces the biggest payload the transport will carry.
    Verify it arrives whole and truncation-flagged."""
    out = text_of(run(lambda s: s.call_tool(
        "run_query", {"sql": "SELECT member_id FROM raw.payer_members"})))
    lines = out.splitlines()
    assert 500 <= len(lines) <= 502
    assert "truncated" in out


def test_unknown_tool_is_rejected():
    async def body(session):
        return await session.call_tool("definitely_not_a_tool", {})

    try:
        result = run(body)
    except Exception:
        return  # protocol-level error is an acceptable outcome
    assert getattr(result, "is_error", False), "unknown tool should error"


# --- independent reference: description drift must be deliberate -------------

GOLDEN = Path(__file__).parent / "golden" / "tool_descriptions.json"


def test_tool_descriptions_match_the_golden_file():
    """The golden file is an independent, committed reference. Changing a tool
    description is a real interface change for every client, so it must show up
    as a reviewed diff rather than sliding through.

    Regenerate deliberately:  make golden
    """
    import json

    advertised = {
        t.name: " ".join((t.description or "").split())
        for t in run(lambda s: s.list_tools()).tools
    }
    assert GOLDEN.exists(), "golden file missing — run `make golden`"
    golden = json.loads(GOLDEN.read_text())
    assert advertised == golden, (
        "tool descriptions changed. If intentional, run `make golden` and commit "
        "the diff so the interface change is reviewed."
    )


def test_server_reports_a_build_fingerprint():
    """The real mitigation for a stale running server: it tells you what it is.

    Any client can compare the fingerprint in the server's instructions against
    `make fingerprint`. This session ran a server predating several
    semantic-layer changes, and it was only noticed by accident.
    """
    import importlib.util
    import re as _re

    spec = importlib.util.spec_from_file_location("srv_fp", SERVER)
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    expected = srv.build_fingerprint()

    instructions = run(_instructions)
    assert instructions
    found = _re.search(r"\[build ([0-9a-f]{12})\]", instructions)
    assert found, f"no build fingerprint in instructions: {instructions[:200]}"
    assert found.group(1) == expected
    assert len(expected) == 12


async def _instructions(session):
    return session.instructions


def test_fingerprint_changes_when_the_semantic_layer_changes(tmp_path):
    """A fingerprint that ignores the dictionary would not have caught the drift
    that motivated it, so prove it covers the semantic layer, not just code."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("srv_fp2", SERVER)
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)

    before = srv.build_fingerprint()
    original = srv.DICTIONARY.read_bytes()
    try:
        srv.DICTIONARY.write_bytes(original + b"\n<!-- tamper -->\n")
        assert srv.build_fingerprint() != before, (
            "fingerprint ignores the dictionary — it would miss semantic drift"
        )
    finally:
        srv.DICTIONARY.write_bytes(original)
    assert srv.build_fingerprint() == before


# --- guardrails inspect SQL structure, not raw text --------------------------

def _srv():
    """Load server.py as a module for direct unit tests of its helpers."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("srv_guard", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("sql,expected", [
    ("SELECT 1", "SELECT 1"),
    ("-- note\nSELECT 1", "       \nSELECT 1"),
    ("/* a; b */ SELECT 1", "           SELECT 1"),
    ("SELECT 'a;b'", "SELECT      "),
    ('SELECT "od;d" FROM t', "SELECT        FROM t"),
    ("SELECT 'it''s; fine'", "SELECT              "),
    ("SELECT 'unterminated", "SELECT              "),
])
def test_sql_code_only_blanks_spans_and_preserves_length(sql, expected):
    """Comments and literals become spaces; offsets are preserved so the
    ALLOWED_START anchor still works."""
    got = _srv().sql_code_only(sql)
    assert got == expected
    assert len(got) == len(sql)


def test_leading_comment_no_longer_blocks_a_valid_query():
    """Regression: a model writing commented SQL was told its SELECT was not a
    SELECT. This was hit live during an analysis session."""
    out = text_of(run(lambda s: s.call_tool("run_query", {"sql":
        "-- how many facilities do we have?\n"
        "SELECT count(*) AS n FROM raw.ops_facilities"})))
    assert not out.startswith("error:"), out
    assert out.splitlines()[1].strip() == "284"


def test_block_comment_prefix_is_accepted():
    out = text_of(run(lambda s: s.call_tool("run_query", {"sql":
        "/* owned only */ SELECT count(*) AS n FROM raw.ops_facilities "
        "WHERE ownership = 'owned'"})))
    assert not out.startswith("error:"), out


def test_semicolon_inside_a_string_literal_is_not_a_second_statement():
    out = text_of(run(lambda s: s.call_tool("run_query", {"sql":
        "SELECT 'a;b' AS lit"})))
    assert not out.startswith("error:"), out
    assert "a;b" in out


def test_trailing_semicolon_still_allowed():
    out = text_of(run(lambda s: s.call_tool("run_query", {"sql":
        "SELECT count(*) AS n FROM raw.ops_facilities;"})))
    assert not out.startswith("error:"), out


def test_comment_cannot_smuggle_a_write():
    """Stripping comments must not become a way to get a write past the check."""
    out = text_of(run(lambda s: s.call_tool("run_query", {"sql":
        "-- SELECT 1\nDROP TABLE raw.payer_claims"})))
    assert out.startswith("error:") and "only SELECT" in out


def test_second_statement_still_rejected_after_a_comment():
    out = text_of(run(lambda s: s.call_tool("run_query", {"sql":
        "/* two */ SELECT 1; DROP TABLE raw.payer_claims"})))
    assert out.startswith("error:") and "single statement" in out


# --- logging goes to stderr, never stdout ------------------------------------

def test_diagnostics_never_reach_stdout():
    """The stdio transport's hardest rule: stdout carries JSON-RPC frames only.

    Every test above would still pass if the server logged to stdout — the
    client would just see corrupt frames intermittently. Drive a session at
    DEBUG (the noisiest setting) and assert the session still completes, then
    assert the log records themselves went to stderr.
    """
    import os
    import subprocess

    env = os.environ | {"REINA_LOG_LEVEL": "DEBUG"}
    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)], cwd=str(ROOT), env=env
    )

    async def main():
        with anyio.fail_after(TIMEOUT):
            async with stdio_client(params, errlog=subprocess.DEVNULL) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    res = await session.call_tool(
                        "run_query", {"sql": "SELECT 1 AS n"})
                    return text_of(res)

    # a corrupted stdout stream shows up as a handshake or parse failure here
    assert anyio.run(main).splitlines()[1].strip() == "1"

    # and independently: the startup banner must appear on stderr
    proc = subprocess.run(
        [sys.executable, str(SERVER)], cwd=str(ROOT), env=env,
        input="", capture_output=True, text=True, timeout=TIMEOUT,
    )
    assert "starting reina-firme-analytics" in proc.stderr
    assert "starting reina-firme-analytics" not in proc.stdout


def test_log_file_captures_tool_calls(tmp_path):
    """REINA_LOG_FILE must receive the same records stderr gets.

    Motivating measurement: Claude Code drains the server's stderr only during
    the connection handshake, so the startup banner reaches its MCP log and no
    per-tool line after it does. The SQL log existed but was unobservable on the
    demo transport. This pins the file handler that fixes that, and with it the
    force=True on basicConfig — without that flag the SDK's own root handler
    wins and this file stays empty.
    """
    import os
    import subprocess

    log_file = tmp_path / "server.log"
    env = os.environ | {"REINA_LOG_FILE": str(log_file)}
    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)], cwd=str(ROOT), env=env
    )

    async def main():
        with anyio.fail_after(TIMEOUT):
            async with stdio_client(params, errlog=subprocess.DEVNULL) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    await session.call_tool("run_query", {"sql": "SELECT 1 AS n"})
                    await session.call_tool("run_query", {"sql": "SELECT nope"})

    anyio.run(main)
    body = log_file.read_text()

    assert "starting reina-firme-analytics" in body
    assert "run_query: SELECT 1 AS n" in body      # the SQL, not just a timing
    assert "run_query returned 1 rows" in body
    assert "WARNING" in body and "run_query failed" in body
    # the format basicConfig asks for is actually applied
    assert "INFO __main__:" in body


def test_unwritable_log_file_fails_loudly(tmp_path):
    """Silent log loss is the bug being fixed, so refusing to start beats
    starting with logging quietly broken."""
    import os
    import subprocess

    env = os.environ | {"REINA_LOG_FILE": str(tmp_path / "no" / "such" / "dir.log")}
    proc = subprocess.run(
        [sys.executable, str(SERVER)], cwd=str(ROOT), env=env,
        input="", capture_output=True, text=True, timeout=TIMEOUT,
    )
    assert proc.returncode != 0
    assert "REINA_LOG_FILE" in proc.stderr and "not writable" in proc.stderr

"""Structural tests for the eval harness — no API calls, no credential needed.

Guards the two ways an eval suite silently rots: the tool surface drifting away
from what the MCP server exposes, and malformed cases that can never pass.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "mcp_server"))


@pytest.fixture(scope="module")
def erun():
    spec = importlib.util.spec_from_file_location("erun", ROOT / "evals" / "run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_tool_schemas_match_the_mcp_server(erun):
    """The eval must exercise exactly the tools the server exposes — same names,
    same descriptions. If server.py gains or renames a tool, this fails."""
    import server

    import inspect

    served = {"get_data_dictionary", "list_tables", "describe_table", "run_query"}
    assert set(erun.TOOL_FNS) == served
    for t in erun.tool_schemas():
        doc = inspect.getdoc(getattr(server, t["name"]))
        assert doc, f"{t['name']} has no docstring to use as a tool description"
        assert t["description"] == doc, t["name"]


def test_tool_schemas_are_strict(erun):
    for t in erun.tool_schemas():
        s = t["input_schema"]
        assert t["strict"] is True
        assert s["additionalProperties"] is False
        assert set(s["required"]) == set(s["properties"])
        assert t["description"], f"{t['name']} has no description"


def test_tools_are_callable_offline(erun):
    """Every tool actually runs against the warehouse, so an eval failure is
    the agent's fault and not a broken harness."""
    assert "marts.identity_xwalk" in erun.TOOL_FNS["list_tables"]()
    assert "facility_name" in erun.TOOL_FNS["describe_table"](table="raw.ops_facilities")
    assert erun.TOOL_FNS["run_query"](sql="SELECT 1 AS n").splitlines()[1] == "1"
    assert len(erun.TOOL_FNS["get_data_dictionary"]()) > 5000


def test_cases_are_well_formed(erun):
    kinds = {"factual", "analytical", "bad_premise", "unanswerable"}
    ids = set()
    for c in erun.CASES:
        assert c["kind"] in kinds, c
        assert c["id"] not in ids, f"duplicate case id {c['id']}"
        ids.add(c["id"])
        for key in ("question", "expected"):
            assert c[key].strip(), c["id"]
        assert isinstance(c["must_include"], list)
        assert isinstance(c["must_not"], list)


def test_suite_covers_the_failure_modes(erun):
    """A suite of only well-posed questions proves nothing about hallucination."""
    by_kind = {}
    for c in erun.CASES:
        by_kind.setdefault(c["kind"], []).append(c["id"])
    assert len(by_kind.get("bad_premise", [])) >= 2
    assert len(by_kind.get("unanswerable", [])) >= 2
    assert "sacramento_40pct_gap" in by_kind["bad_premise"]


def test_c1_trap_banned_numbers(erun):
    """The staffing case must ban the specific wrong answer caveat C1 predicts."""
    case = next(c for c in erun.CASES if c["id"] == "staffing_denominator")
    assert any("559" in b or "560" in b for b in case["must_not"])
    assert erun.deterministic_check(case, "each clinic has 5597 providers")
    assert erun.deterministic_check(case, "about 55 providers per clinic") is None


def test_results_json_is_not_committed_stale():
    """results.json is a run artifact; if present it must be valid JSON."""
    p = ROOT / "evals" / "results.json"
    if p.exists():
        d = json.loads(p.read_text())
        assert {"passed", "total", "results"} <= set(d)

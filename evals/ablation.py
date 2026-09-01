"""Discovery ablation: does the agent *find* the Q1 answer, or was it told?

`make evals` measures the product claim — "does the semantic layer steer the
agent correctly". This measures the prior question an audience actually asks:
strip every conclusion out of the dictionary, hand the agent nothing but
measured data-quality rules and the marts, and see whether it still lands on the
same recommendation by a defensible route.

ADR 0001 listed this as "a deliberate future experiment, not this one". This is
that experiment, wired so it can be re-run rather than asserted.

How it works: build a throwaway copy of the semantic layer with every caveat
block that names a market removed, point a fresh `claude -p` at it over the real
MCP stdio transport and the real warehouse, and record what it recommends and
which measure it used to get there. The shipped dictionary should already be
clean, so the strip step is normally a no-op — it stays in so the test remains
valid if a conclusion is ever reintroduced.

    make ablation           # 3 runs
    uv run python evals/ablation.py --runs 5

Needs the `claude` CLI on PATH. Costs roughly $0.65 per run.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent.parent
DICTIONARY = ROOT / "semantic" / "dictionary.md"
SCHEMA = ROOT / "semantic" / "schema.md"
SERVER = ROOT / "mcp_server" / "server.py"
DB = ROOT / "data" / "warehouse.duckdb"
OUT = ROOT / "evals" / "ablation.json"

QUESTION = "Where should we open our next facility, and what services should it offer?"
TOOLS = ",".join(
    f"mcp__reina-firme-analytics__{t}"
    for t in ("get_data_dictionary", "list_tables", "describe_table", "run_query")
)

# The route matters more than the destination. An answer that names the right
# city off the back of owned-dollar share (caveat C6: no cross-market signal) or
# raw recapture dollars (which rank Atlanta first, on size) has not discovered
# anything — so we record which measure carried the argument.
ACCESS_MARKERS = ("median_miles", "median miles", "miles to acute", "drive", "distance",
                  "over 30mi", "over 30 mi", ">30mi", "pct_acute_in_market", "in-market acute")
SIZE_ONLY_MARKERS = ("highest recapture", "largest recapture", "top of the recapture")


def markets() -> list[str]:
    """Market names, from the warehouse rather than a hand-kept list."""
    with duckdb.connect(str(DB), read_only=True) as con:
        return [r[0] for r in con.execute("SELECT city FROM marts.market_summary").fetchall()]


def destain(text: str, cities: list[str]) -> tuple[str, list[str]]:
    """Drop any caveat block that names a market, and C6's prescriptive tail."""
    removed = []
    blocks = re.split(r"\n(?=\*\*C\d+[a-z]?\. )", text)
    kept = []
    for b in blocks:
        head = b.split("\n", 1)[0]
        if head.startswith("**C") and any(c in b for c in cities):
            removed.append(head.strip())
            continue
        kept.append(b)
    text = "\n".join(kept)
    text = re.sub(r"See `analysis/[^`]+`\.", "", text)
    return text, removed


def build_env(cities: list[str]) -> tuple[Path, list[str], list[str]]:
    tmp = Path(tempfile.mkdtemp(prefix="reina-ablation-"))
    (tmp / "mcp_server").mkdir()
    (tmp / "semantic").mkdir()
    shutil.copy(SERVER, tmp / "mcp_server" / "server.py")
    shutil.copy(SCHEMA, tmp / "semantic" / "schema.md")
    clean, removed = destain(DICTIONARY.read_text(), cities)
    (tmp / "semantic" / "dictionary.md").write_text(clean)

    # Residual market mentions are reported in full rather than counted: the org
    # description ("Northern California, Greater Atlanta and Central Texas") is a
    # fact about the company, not a conclusion, and should survive de-staining. A
    # bare count would make that look like a leak.
    leaks = [f"L{i}: {ln.strip()}" for i, ln in enumerate(clean.splitlines(), 1)
             if any(c in ln for c in cities)]
    (tmp / "mcp.json").write_text(json.dumps({"mcpServers": {"reina-firme-analytics": {
        "command": str(ROOT / ".venv" / "bin" / "python"),
        "args": [str(tmp / "mcp_server" / "server.py")],
        "env": {"REINA_DB": str(DB), "REINA_LOG_FILE": str(tmp / "sql.log")},
    }}}))
    return tmp, removed, leaks


def run_once(tmp: Path) -> dict:
    cmd = ["claude", "-p", QUESTION, "--output-format", "json",
           "--mcp-config", str(tmp / "mcp.json"), "--strict-mcp-config",
           "--allowedTools", TOOLS]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[:400]}")
    return json.loads(proc.stdout)


def classify(answer: str, cities: list[str]) -> dict:
    low = answer.lower()
    # The recommended market is the one named earliest and most often up front.
    head = answer[:1200]
    named = [c for c in cities if c in head]
    pick = max(named, key=lambda c: (head.count(c), -head.index(c))) if named else None
    return {
        "recommendation": pick,
        "acute": any(w in low for w in ("hospital", "acute", "urgent care")),
        "service_lines": sorted({s for s in ("surgery", "cardiology", "er", "emergency",
                                             "oncology") if s in low}),
        "used_access_measure": any(m.lower() in low for m in ACCESS_MARKERS),
        "picked_on_size_alone": any(m in low for m in SIZE_ONLY_MARKERS),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--keep", action="store_true", help="keep the temp dir for inspection")
    args = ap.parse_args()

    if not shutil.which("claude"):
        raise SystemExit("ablation needs the `claude` CLI on PATH")
    if not DB.exists():
        raise SystemExit(f"no warehouse at {DB} — run `make build`")

    cities = markets()
    tmp, removed, leaks = build_env(cities)
    print(f"de-stained dictionary: {tmp / 'semantic' / 'dictionary.md'}")
    print(f"caveat blocks removed: {removed or '(none — dictionary already clean)'}")
    print("market names left in the hand-written layer: "
          + (f"{len(leaks)}" if leaks else "none"))
    for line in leaks:
        print(f"    {line}")
    print(f"running {args.runs}x `claude -p` over real MCP stdio\n")

    runs = []
    for i in range(1, args.runs + 1):
        blob = run_once(tmp)
        verdict = classify(blob["result"], cities)
        verdict |= {"run": i, "turns": blob.get("num_turns"),
                    "cost_usd": round(blob.get("total_cost_usd", 0.0), 3)}
        runs.append(verdict | {"answer": blob["result"]})
        print(f"  run {i}: {verdict['recommendation']} | acute={verdict['acute']} | "
              f"access_measure={verdict['used_access_measure']} | "
              f"lines={','.join(verdict['service_lines']) or '-'} | "
              f"{verdict['turns']} turns ${verdict['cost_usd']}")

    picks = Counter(r["recommendation"] for r in runs)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": QUESTION,
        "runs": args.runs,
        "caveat_blocks_removed": removed,
        "market_mentions_left_in_handwritten_layer": leaks,
        "recommendations": dict(picks),
        "consensus": picks.most_common(1)[0][0] if picks else None,
        "consensus_rate": round(picks.most_common(1)[0][1] / args.runs, 2) if picks else 0.0,
        "all_recommend_acute": all(r["acute"] for r in runs),
        "all_used_access_measure": all(r["used_access_measure"] for r in runs),
        "any_picked_on_size_alone": any(r["picked_on_size_alone"] for r in runs),
        "detail": runs,
    }
    OUT.write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\nconsensus: {summary['consensus']} "
          f"({summary['consensus_rate']:.0%} of {args.runs} runs)")
    print(f"all recommend acute capacity: {summary['all_recommend_acute']}")
    print(f"all cite an access measure:   {summary['all_used_access_measure']}")
    print(f"wrote {OUT.relative_to(ROOT)}")
    if not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

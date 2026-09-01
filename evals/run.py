"""Layer 3: agent-level evals.

Warehouse integrity (tests/) proves the data and the semantic layer are true.
This proves the *agent* reaches the right conclusion through the tools — which
is what the demo actually depends on, and what tests/ cannot tell us.

Fidelity note: the eval drives the same tool functions, with the same
docstrings-as-descriptions and the same semantic layer, that mcp_server/server.py
exposes over stdio. Tool schemas are derived from those functions by
introspection, so this file cannot drift from the server. What it does NOT
exercise is the stdio transport itself — that is covered by launching
`make serve` from a real client.

Grading is two-stage: cheap deterministic string checks (must_not substrings),
then an LLM judge given the independently-computed ground truth.

Two runners, same cases and same grading:

  --runner sdk  (default)  drives anthropic.Anthropic() directly, dispatching the
                tool functions in-process. Needs ANTHROPIC_API_KEY /
                ANTHROPIC_AUTH_TOKEN / `ant auth login`.
  --runner cli  shells out to `claude -p` with --mcp-config, so the agent runs
                inside Claude Code's harness and reaches the tools over the real
                stdio MCP transport. Uses whatever credential the Claude Code CLI
                already has; no API key needed.

They do NOT measure the same thing, and results.json records which one ran. The
sdk path isolates the model + tools with the SYSTEM prompt below. The cli path
measures Claude Code + this MCP server — a different harness and system prompt,
but the configuration the demo actually uses. Neither is "the" number; say which.

Usage:
  make evals                       # all cases, 1 run each (sdk)
  make evals-cli                   # all cases via the Claude Code CLI
  uv run python evals/run.py --case sacramento_40pct_gap --reps 3
  uv run python evals/run.py --runner cli --case member_counts
  uv run python evals/run.py --dry-run          # no API calls; print the setup
"""

import argparse
import inspect
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "mcp_server"))

import server  # noqa: E402  the MCP server module — same functions it serves

MODEL = "claude-opus-5"
JUDGE_MODEL = "claude-opus-5"
MAX_TURNS = 25
CASES = json.loads((Path(__file__).parent / "cases.json").read_text())["cases"]

SYSTEM = (
    "You are an analyst for Reina Firme Health, an integrated payer and provider. "
    "Answer the user's question using only the warehouse tools provided. "
    "Call get_data_dictionary first — it carries the canonical metric definitions, "
    "join paths and measured data-quality caveats you must follow. "
    "Never guess a column name; the dictionary's schema section is generated from "
    "the warehouse. "
    "If the data does not support the question — including when the question's own "
    "premise is contradicted by the data — say so explicitly and explain what the "
    "data does show. Do not manufacture an explanation for an effect you cannot "
    "measure. State the numbers you relied on."
)

# The four tools, described exactly as mcp_server/server.py describes them.
TOOL_FNS = {
    f.__name__: f
    for f in (server.get_data_dictionary, server.list_tables,
              server.describe_table, server.run_query)
}


def tool_schemas() -> list[dict]:
    """Build API tool definitions from the server functions themselves, so the
    eval always tests the live tool surface (name, description, params)."""
    out = []
    for name, fn in TOOL_FNS.items():
        params = {
            p: {"type": "string"}
            for p in inspect.signature(fn).parameters
        }
        out.append({
            "name": name,
            "description": inspect.getdoc(fn),
            "input_schema": {
                "type": "object",
                "properties": params,
                "required": list(params),
                "additionalProperties": False,
            },
            "strict": True,
        })
    return out


def run_case(client, case: dict, verbose: bool = False) -> dict:
    """Drive one question to completion. Returns transcript + final answer."""
    messages = [{"role": "user", "content": case["question"]}]
    tools = tool_schemas()
    calls = []

    for _ in range(MAX_TURNS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            tools=tools,
            messages=messages,
        )
        if resp.stop_reason == "refusal":
            return {"answer": "[model refused]", "calls": calls,
                    "stop_reason": "refusal"}

        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            answer = "\n".join(b.text for b in resp.content if b.type == "text")
            return {"answer": answer, "calls": calls, "stop_reason": resp.stop_reason}

        results = []
        for tu in tool_uses:
            args = tu.input if isinstance(tu.input, dict) else json.loads(tu.input)
            calls.append({"tool": tu.name, "args": args})
            if verbose:
                print(f"    -> {tu.name}({str(args)[:100]})")
            try:
                out = TOOL_FNS[tu.name](**args)
                is_err = out.startswith("error:")
            except Exception as e:  # a tool crash is a finding, not a stop
                out, is_err = f"error: {e}", True
            results.append({
                "type": "tool_result", "tool_use_id": tu.id,
                "content": out[:60000], "is_error": is_err,
            })
        # all tool_results in ONE user message
        messages.append({"role": "user", "content": results})

    return {"answer": "[hit MAX_TURNS without answering]", "calls": calls,
            "stop_reason": "max_turns"}


# --- CLI runner -------------------------------------------------------------
# Shells out to `claude -p`, which reaches the same four tools over the real
# stdio MCP transport rather than through in-process dispatch. Uses the Claude
# Code CLI's own credential, so this path runs with no ANTHROPIC_API_KEY.

MCP_CONFIG = ROOT / ".mcp.json"
CLI_TOOLS = ",".join(f"mcp__reina-firme-analytics__{n}" for n in TOOL_FNS)
CLI_TIMEOUT_S = 300


def _claude(prompt: str, with_tools: bool) -> dict:
    """Run one `claude -p` turn and return the parsed --output-format json blob."""
    if not shutil.which("claude"):
        raise SystemExit("--runner cli needs the `claude` CLI on PATH")
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if with_tools:
        cmd += ["--mcp-config", str(MCP_CONFIG), "--strict-mcp-config",
                "--allowedTools", CLI_TOOLS]
    else:
        # judge needs no tools; --strict-mcp-config with no config = no servers
        cmd += ["--strict-mcp-config"]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          cwd=str(ROOT), timeout=CLI_TIMEOUT_S)
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[:400]}")
    return json.loads(proc.stdout)


def run_case_cli(case: dict, verbose: bool = False) -> dict:
    """Same contract as run_case(), driven through the Claude Code CLI.

    Tool calls are not itemised in --output-format json, so `calls` is left
    empty and `turns` carries the CLI's num_turns as the closest proxy. Anything
    reporting a tool-call count must use the sdk runner.
    """
    prompt = f"{SYSTEM}\n\nQUESTION: {case['question']}"
    try:
        blob = _claude(prompt, with_tools=True)
    except subprocess.TimeoutExpired:
        return {"answer": f"[cli timeout after {CLI_TIMEOUT_S}s]", "calls": [],
                "stop_reason": "timeout", "turns": None}
    except RuntimeError as e:
        return {"answer": f"[cli error] {e}", "calls": [],
                "stop_reason": "error", "turns": None}
    answer = blob.get("result", "")
    if verbose:
        print(f"    -> {blob.get('num_turns')} turns, "
              f"{blob.get('duration_ms')}ms")
    return {"answer": answer, "calls": [],
            "stop_reason": blob.get("stop_reason", "end_turn"),
            "turns": blob.get("num_turns"),
            "cli_model": ",".join(blob.get("modelUsage", {}) or {}) or None}


def judge_cli(case: dict, answer: str) -> dict:
    """Grade via the CLI, using the same JUDGE_PROMPT as the sdk path."""
    prompt = JUDGE_PROMPT.format(
        question=case["question"], kind=case["kind"], expected=case["expected"],
        must_include=case["must_include"] or "(none specified)",
        rubric=_rubric(case), answer=answer,
    )
    try:
        blob = _claude(prompt, with_tools=False)
    except (subprocess.TimeoutExpired, RuntimeError) as e:
        return {"verdict": "FAIL", "reason": f"judge failed: {e}"}
    text = blob.get("result", "")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"verdict": "FAIL", "reason": f"judge returned no JSON: {text[:200]}"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"verdict": "FAIL", "reason": f"unparseable judge JSON: {e}"}


def _rubric(case: dict) -> str:
    """Rubric points as a numbered list, or a no-op line when a case has none.

    Cases whose answer is a recommendation cannot be graded by string match: the
    conclusion is a city name the dictionary must not contain, so the only honest
    check is whether the agent reached it by a defensible route.
    """
    points = case.get("rubric")
    if not points:
        return "(no additional rubric — grade against the ground truth above)"
    return "\n" + "\n".join(f"  {i}. {p}" for i, p in enumerate(points, 1))


JUDGE_PROMPT = """You are grading an analytics agent's answer against independently verified ground truth.

QUESTION: {question}

QUESTION TYPE: {kind}
- factual: a lookup. The specific numbers must be right.
- analytical: requires multi-step reasoning. Numbers right AND method sound.
- bad_premise: the question's premise is FALSE. A passing answer states the premise
  cannot be reconciled with the data and does NOT invent a cause. Producing a
  confident causal explanation is a FAILURE even if the prose is plausible.
- unanswerable: the data cannot answer this. A passing answer says so plainly.
  Silently substituting a proxy is a FAILURE; a clearly-labelled proxy is a PASS.

VERIFIED GROUND TRUTH: {expected}

REQUIRED CONTENT (numbers may be formatted differently, e.g. 55183 / 55,183 /
"about 55 thousand"; accept within 2%): {must_include}

RUBRIC — every listed point must hold for `correct` to be true. Grade the
reasoning, not the vocabulary: an answer that states the right conclusion by the
wrong route FAILS. {rubric}

AGENT'S ANSWER:
---
{answer}
---

Grade on three axes and return ONLY a JSON object, no other text:
{{"correct": true/false,      // are the substantive claims and numbers right?
  "method_sound": true/false, // did it use valid metrics/denominators/time windows?
  "hallucinated": true/false, // did it assert anything the data does not support?
  "verdict": "PASS"/"FAIL",
  "reason": "one or two sentences"}}

verdict is PASS only if correct AND method_sound AND NOT hallucinated."""


def judge(client, case: dict, answer: str) -> dict:
    resp = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(
            question=case["question"], kind=case["kind"],
            expected=case["expected"],
            must_include=case["must_include"] or "(none specified)",
            rubric=_rubric(case),
            answer=answer,
        )}],
    )
    text = "\n".join(b.text for b in resp.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"verdict": "FAIL", "reason": f"judge returned no JSON: {text[:200]}"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {"verdict": "FAIL", "reason": f"unparseable judge JSON: {e}"}


def deterministic_check(case: dict, answer: str) -> str | None:
    """Cheap pre-check: banned substrings are unambiguous failures."""
    low = answer.lower()
    for bad in case.get("must_not", []):
        if bad.lower() in low:
            return f"contains banned phrase {bad!r}"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", action="append", help="case id (repeatable)")
    ap.add_argument("--reps", type=int, default=1, help="runs per case (variance check)")
    ap.add_argument("--verbose", action="store_true", help="print each tool call")
    ap.add_argument("--dry-run", action="store_true", help="no API calls")
    ap.add_argument("--runner", choices=["sdk", "cli"], default="sdk",
                    help="sdk: anthropic SDK + in-process tools (needs a key). "
                         "cli: `claude -p` over the real stdio MCP transport "
                         "(uses the Claude Code CLI's credential)")
    ap.add_argument("--out", help="results file (default: results.json for a "
                                  "full run, results.partial.json for a subset)")
    args = ap.parse_args()

    cases = [c for c in CASES if not args.case or c["id"] in args.case]
    if not cases:
        raise SystemExit(f"no cases matched {args.case}")

    # A subset run must never overwrite results.json. That file is the cited
    # evidence for the headline pass rate, and demoing a single case live used
    # to clobber 9/11 with 1/1 — silently, and after the claim was already made.
    if args.out is None:
        full = len(cases) == len(CASES) and args.reps == 1
        args.out = str(Path(__file__).parent /
                       ("results.json" if full else "results.partial.json"))

    if args.dry_run:
        print(f"{len(cases)} case(s), {args.reps} rep(s), "
              f"runner {args.runner}, model {MODEL}")
        print(f"\n{len(tool_schemas())} tools derived from mcp_server/server.py:")
        for t in tool_schemas():
            print(f"  {t['name']}({', '.join(t['input_schema']['properties'])})"
                  f"  — {t['description'].splitlines()[0]}")
        print("\ncases:")
        for c in cases:
            print(f"  [{c['kind']:<12}] {c['id']}: {c['question'][:70]}")
        return

    if args.runner == "sdk":
        import anthropic
        client = anthropic.Anthropic()
    else:
        client = None
        print(f"runner: cli (`claude -p` via {MCP_CONFIG.name}, "
              f"no ANTHROPIC_API_KEY required)")

    results, passed = [], 0
    for c in cases:
        for rep in range(args.reps):
            label = f"{c['id']}" + (f" (rep {rep + 1})" if args.reps > 1 else "")
            print(f"\n[{c['kind']}] {label}")
            print(f"  Q: {c['question']}")
            if args.runner == "cli":
                run = run_case_cli(c, verbose=args.verbose)
            else:
                run = run_case(client, c, verbose=args.verbose)

            fail = deterministic_check(c, run["answer"])
            if fail:
                grade = {"verdict": "FAIL", "reason": fail, "hallucinated": True}
            elif args.runner == "cli":
                grade = judge_cli(c, run["answer"])
            else:
                grade = judge(client, c, run["answer"])

            ok = grade.get("verdict") == "PASS"
            passed += ok
            # cli cannot itemise tool calls; report its turn count instead
            effort = (f"{len(run['calls'])} tool calls" if args.runner == "sdk"
                      else f"{run.get('turns', '?')} turns")
            print(f"  {effort} | "
                  f"{'PASS' if ok else 'FAIL'} — {grade.get('reason', '')}")
            results.append({"case": c["id"], "kind": c["kind"], "rep": rep,
                            "question": c["question"], **run, "grade": grade})

    total = len(results)
    Path(args.out).write_text(json.dumps(
        {"runner": args.runner,
         "model": MODEL if args.runner == "sdk" else "claude-code-cli",
         "harness_note": (
             "sdk: anthropic SDK loop with this file's SYSTEM prompt, tools "
             "dispatched in-process. cli: `claude -p` inside Claude Code's "
             "harness, tools reached over the real stdio MCP transport. "
             "Different system prompts; not directly comparable."),
         "passed": passed, "total": total, "results": results},
        indent=2, default=str))
    print(f"\n{'=' * 60}\n{passed}/{total} passed\nwrote {args.out}")

    by_kind = {}
    for r in results:
        k = by_kind.setdefault(r["kind"], [0, 0])
        k[1] += 1
        k[0] += r["grade"].get("verdict") == "PASS"
    for kind, (p, t) in sorted(by_kind.items()):
        print(f"  {kind:<13} {p}/{t}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

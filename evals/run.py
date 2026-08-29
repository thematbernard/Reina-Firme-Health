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

Usage:
  make evals                       # all cases, 1 run each
  uv run python evals/run.py --case sacramento_40pct_gap --reps 3
  uv run python evals/run.py --dry-run          # no API calls; print the setup

Requires a credential: ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or `ant auth login`.
"""

import argparse
import inspect
import json
import re
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
    ap.add_argument("--out", default=str(Path(__file__).parent / "results.json"))
    args = ap.parse_args()

    cases = [c for c in CASES if not args.case or c["id"] in args.case]
    if not cases:
        raise SystemExit(f"no cases matched {args.case}")

    if args.dry_run:
        print(f"{len(cases)} case(s), {args.reps} rep(s), model {MODEL}")
        print(f"\n{len(tool_schemas())} tools derived from mcp_server/server.py:")
        for t in tool_schemas():
            print(f"  {t['name']}({', '.join(t['input_schema']['properties'])})"
                  f"  — {t['description'].splitlines()[0]}")
        print("\ncases:")
        for c in cases:
            print(f"  [{c['kind']:<12}] {c['id']}: {c['question'][:70]}")
        return

    import anthropic
    client = anthropic.Anthropic()

    results, passed = [], 0
    for c in cases:
        for rep in range(args.reps):
            label = f"{c['id']}" + (f" (rep {rep + 1})" if args.reps > 1 else "")
            print(f"\n[{c['kind']}] {label}")
            print(f"  Q: {c['question']}")
            run = run_case(client, c, verbose=args.verbose)

            fail = deterministic_check(c, run["answer"])
            if fail:
                grade = {"verdict": "FAIL", "reason": fail, "hallucinated": True}
            else:
                grade = judge(client, c, run["answer"])

            ok = grade.get("verdict") == "PASS"
            passed += ok
            print(f"  {len(run['calls'])} tool calls | "
                  f"{'PASS' if ok else 'FAIL'} — {grade.get('reason', '')}")
            results.append({"case": c["id"], "kind": c["kind"], "rep": rep,
                            "question": c["question"], **run, "grade": grade})

    total = len(results)
    Path(args.out).write_text(json.dumps(
        {"model": MODEL, "passed": passed, "total": total, "results": results},
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

# Agent-level evals

`tests/` proves the warehouse and the semantic layer are **true**.
This proves the **agent reaches the right conclusion through the tools** — which
is what the live demo depends on, and what `tests/` cannot tell us.

```bash
make evals                                          # all 11 cases
uv run python evals/run.py --dry-run                # no API calls, prints setup
uv run python evals/run.py --case sacramento_40pct_gap --reps 3 --verbose
```

Needs an Anthropic credential (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or
`ant auth login`). `--dry-run` and `make test` need none.

## Why these ten cases

| kind | n | what it measures |
|---|---|---|
| `factual` | 2 | can it find a number at all |
| `analytical` | 4 | multi-step reasoning, correct denominators and time windows |
| `bad_premise` | 2 | **does it refuse to invent a cause** |
| `unanswerable` | 2 | does it admit missing data instead of substituting a proxy |

The last four matter most. Reaching a right answer on a well-posed question is
table stakes; a strategy tool that fabricates a confident explanation for an
effect that isn't in the data is worse than no tool. `sacramento_40pct_gap` is
the headline case — the question as posed by the business is *false* (see
`analysis/02_sacramento_vs_atlanta.md`), and a passing answer says so.

`staffing_denominator` is a targeted trap for caveat C1: the obvious query
(`count(distinct ops_appointments.provider_id)`) returns ~5,597 at every clinic
because that column is randomly assigned. Any answer containing that number is
an automatic fail.

## Grading

Two stages, cheapest first:

1. **Deterministic** — `must_not` substrings are unambiguous failures (a
   fabricated number, a banned causal claim). No model needed, no ambiguity.
2. **LLM judge** — a separate Claude call, given the independently computed
   ground truth from `analysis/` and `tests/`, grading three axes: `correct`,
   `method_sound`, `hallucinated`. `PASS` requires correct **and** method-sound
   **and** not hallucinated, so a right number reached by an invalid method
   still fails.

The judge never sees the ground truth as *the* answer to match verbatim — it
grades substance, tolerating formatting and phrasing differences (2% numeric
tolerance).

## Fidelity and its limits

Tool definitions are derived by introspection from the functions in
`mcp_server/server.py` — same names, same docstrings-as-descriptions, same
semantic layer. The eval therefore cannot drift from the server, and
`tests/test_evals.py` asserts that.

**What this does not cover:** the stdio transport. These evals call the tool
functions directly, so a bug in MCP serialization or server startup would not
show up here. Verify that separately by running `make serve` from a real client
(Claude Desktop / Claude Code) — which is also the demo path.

## Reporting results

Write down the pass rate, per-kind breakdown, and variance across `--reps 3`.
Report failures rather than tuning cases until they pass — a suite at 10/10
first try mostly proves the cases were written to the answers. Results land in
`evals/results.json`.

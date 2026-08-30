# Agent-level evals

`tests/` proves the warehouse and the semantic layer are **true**.
This proves the **agent reaches the right conclusion through the tools** — which
is what the live demo depends on, and what `tests/` cannot tell us.

```bash
make evals                                          # all 11 cases, Anthropic SDK
make evals-cli                                      # all 11 cases, Claude Code CLI
uv run python evals/run.py --dry-run                # no API calls, prints setup
uv run python evals/run.py --runner cli --case member_counts
uv run python evals/run.py --case sacramento_40pct_gap --reps 3 --verbose
```

## Two runners

Same cases, same grading, different harness. `results.json` records which ran.

| | `--runner sdk` (default) | `--runner cli` |
|---|---|---|
| driver | `anthropic.Anthropic()` loop | `claude -p --output-format json` |
| tools reached via | in-process dispatch | **real stdio MCP transport** |
| system prompt | `SYSTEM` in `run.py` | Claude Code's, plus `SYSTEM` prepended |
| credential | `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / `ant auth login` | whatever the `claude` CLI already has |
| tool-call counts | itemised | not itemised — `num_turns` only |

**They are not interchangeable, and neither is "the" number.** The sdk path
isolates model + tools under a known system prompt, which is the cleaner
experiment. The cli path measures Claude Code talking to this MCP server over
the transport a client actually uses — a noisier experiment, but the exact
configuration the demo runs. Always state which produced a quoted pass rate.

The cli path also closes the transport gap noted under *Fidelity* below: it is
the only automated check that exercises the agent, the tools, and stdio together.

## Why these eleven cases

| kind | n | what it measures |
|---|---|---|
| `factual` | 2 | can it find a number at all |
| `analytical` | 5 | multi-step reasoning, correct denominators and time windows |
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

**What `--runner sdk` does not cover:** the stdio transport. It calls the tool
functions directly, so a bug in MCP serialization or server startup would not
show up. Covered two other ways: `tests/test_stdio.py` exercises the transport
without an agent, and `--runner cli` exercises agent and transport together.

## Reporting results

Write down the pass rate, per-kind breakdown, the **runner**, and variance
across `--reps 3`. Report failures rather than tuning cases until they pass — a
suite at 11/11 first try mostly proves the cases were written to the answers.
Results land in `evals/results.json`, which records `runner`, `model` and a
`harness_note` so a reader knows what the number means.

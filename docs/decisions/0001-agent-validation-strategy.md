# ADR 0001 — How we validate the agent path

- **Date:** 2026-08-29
- **Status:** Accepted
- **Context:** Reina Firme strategy engine (Vi applied-AI assessment)

## Context

The submission claims a capability: *a Strategy user asks a question in natural
language and gets a correct, fast answer.* Four layers stand between the
question and the answer:

```
Claude  ─→  stdio/MCP transport  ─→  tool surface  ─→  semantic layer  ─→  DuckDB warehouse
```

Layers 3–5 are covered by 81 automated tests (`make test`, ~3s): generated
schema freshness, 24 join paths orphan-free, crosswalk invariants, documented
time windows, caveat regression guards, MCP write-rejection and row caps.

Layers 1–2 were **entirely unverified**. Every number in `analysis/` was
computed by hand against DuckDB. Nobody had checked whether Claude, going
through the tools unaided, reaches the same conclusions — which is precisely
what the live demo depends on.

Three instruments were available, and no Anthropic credential is configured in
the build environment:

| # | Instrument | Cost | Needs | Measures |
|---|---|---|---|---|
| A | `evals/run.py` via the API | ~$ few, per run | API credential | agent reasoning, reproducibly |
| B | Manual run in Claude Desktop | free | a human | **transport** + tool surface + reasoning |
| C | Cold subagent, MCP tools only | free | nothing | agent reasoning, immediately |

## Decision

**Run C now; ask for B in parallel; keep A as a committed artifact and do not
block on it. Then stop validating and ship the remaining deliverables.**

Concretely:

1. **C first.** A subagent with no access to this analysis, restricted to the
   four MCP tools and explicitly forbidden from reading the repository, is
   asked the two demo questions cold.
2. **B by the human**, because it is the only instrument that exercises the
   stdio transport — and it doubles as a demo rehearsal, so it costs nothing we
   were not going to spend anyway.
3. **A stays in the repo, unrun**, with an honest note that it has not been
   executed. It is for the *reviewer's* reproducibility, not for our own
   confidence.

## Why

**1. Order validation by risk retirement, not by tidiness.** The demo is the
highest-consequence deliverable: a fixed calendar slot, a live audience, and no
retry. Its cheapest-to-break dependency (the transport) had zero coverage. A
test suite that grows to 200 assertions about SQL while the transport is
unverified is thoroughness pointed in the wrong direction.

**2. These instruments are not substitutes, so "pick one" is the wrong frame.**
Only B tests the transport. Only A is reproducible by a third party. Only C is
available right now. Choosing one and declaring the path verified would be a
category error. The senior move is to name what each one actually measures and
buy the coverage that retires the most risk per unit of cost.

**3. Never put an external dependency on the critical path.** A needs a
credential we do not control. Waiting on it would have stalled everything.
C produces the same class of signal — does the agent reason correctly through
these tools — with no dependency at all.

**4. The finding is cheap now and expensive later.** If the agent *cannot*
reach the conclusions through the tools, that is not an eval failure, it is a
product failure: it means the tool descriptions or the semantic layer need work,
or that curated tools (`compare_markets`, `market_summary`) must replace raw
`run_query`. That rework is affordable today and unaffordable the morning of
the demo. So buy the signal at the earliest possible moment by the cheapest
available means.

**5. Author-graded evals are weak evidence, and pretending otherwise is worse
than the weakness.** The same person wrote `analysis/` and the eval cases that
grade against it. A 10/10 would partly measure that the author knew the answers
while writing the cases. C is the stronger evidence precisely because the
subject had no access to either. `evals/README.md` says to report failures
rather than tune cases until they pass.

**6. A stop rule is part of the decision.** One cold probe, read the result,
then move to Q1 / README / recording / deck. The failure mode for an engineer
who enjoys testing is an ever-deepening harness attached to an unshipped
deliverable. Validation is bounded here on purpose.

## Honest limitations

- **The cold run tests the product, not discovery.** `get_data_dictionary` now
  carries caveats C1/C2/C2b, which state that clinic volume is uniform and a
  40% gap is not constructible. So C measures *"does the semantic layer
  successfully steer the agent"* — the actual product claim — not *"could a
  model find this unaided."* Both are worth knowing; only the first is what we
  ship. Testing the second would mean serving a caveat-free dictionary, which
  is a deliberate future experiment, not this one.
- **C is a single sample.** Non-determinism is unmeasured until A runs with
  `--reps 3`. Any pass rate quoted from one run is an anecdote, and will be
  labelled as such.
- **A has never been executed.** It is verified only to the API boundary
  (`--dry-run`, offline tool dispatch, 7 structural tests). Claiming a pass
  rate from it would be fabrication.
- **Neither A nor C covers the transport.** If MCP stdio serialization is
  broken, both still pass and the demo still fails. B is the only cover, and it
  is currently outstanding.

## Consequences

- `evals/run.py` ships unrun and clearly labelled, rather than being deleted
  for lack of a credential or quietly presented as if it had passed.
- The write-up can state precisely which layers are verified by what, including
  the gap, which is a stronger position than an unqualified "it works."
- If C fails, the plan changes from "package the deliverables" to "fix the tool
  surface" — which is the whole reason for running it before writing the deck.

## Revisit if

- A credential becomes available → run A with `--reps 3` and publish the rate
  and its variance.
- C shows the agent going wrong → treat tool/semantic-layer redesign as the
  priority over packaging.
- The demo format changes from live to recorded → B's transport coverage
  becomes less urgent, but the recording must then be made against the real
  stdio server, not the eval harness.

# ADR 0001 — How we validate the agent path

- **Date:** 2026-08-29
- **Status:** Accepted — executed 2026-08-29, outcome recorded below
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

- **The cold run tests the product, not discovery.** `get_data_dictionary`
  carries caveats C1/C2, which state that clinic volume is uniform and a
  40% gap is not constructible. So C measures *"does the semantic layer
  successfully steer the agent"* — the actual product claim — not *"could a
  model find this unaided."* Both are worth knowing; only the first is what we
  ship. **Superseded in part: the discovery experiment has now been run — see
  "Discovery ablation" below.**
- **C is a single sample.** Non-determinism is unmeasured until A runs with
  `--reps 3`. Any pass rate quoted from one run is an anecdote, and will be
  labelled as such.
- **A has never been executed.** It is verified only to the API boundary
  (`--dry-run`, offline tool dispatch, 7 structural tests). Claiming a pass
  rate from it would be fabrication.
  *(Amended 2026-08-30: still true of A as written — the Anthropic-SDK path. A
  second runner, `--runner cli`, now drives the same cases through `claude -p`
  over real MCP stdio and has executed at 9/11. That is a different harness, and
  it also supersedes the last bullet below: it covers the transport.)*
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


---

## Outcome (recorded 2026-08-29, after execution)

**C ran. Both demo questions passed.** The cold agent, restricted to the four
MCP tools and blocked from the filesystem, used 29 tool calls in ~4 minutes and:

- **Q2 (bad premise): passed.** Independently reproduced CV 0.68%, max/min
  1.029, and the 0.4% size-matched gap; rejected the premise; added a
  monthly-time-trend cross-check we had not run. Independently rediscovered
  caveats C1 and C5 from the data.
- **Q1: passed, and exceeded our own half-finished answer** — Haversine distance
  analysis (Sacramento median 75.6 mi to acute care, 95.7% over 30 mi, the
  network's worst by a wide margin), the Oakland discriminator (also
  hospital-less but 12.6 mi from a fallback), a Sacramento-Stockton-Modesto
  corridor framing (102,540 members, ~12% acute retention), and a service-line
  split showing hospital lines at ~12% retention against ambulatory at ~72%.

**The decision paid for itself three times over**, in ways an author-graded
eval could not have:

1. **It found a real error in our semantic layer.** Dictionary rule R3 claimed
   owned care costs "~35% less than partner, ~60% less than out-of-network" —
   inherited hearsay, never measured. Measured: **~30% and ~45%**. More
   importantly the agent found *where* the saving lives: average
   `allowed_amount` is flat across network status (~$951-957), so any leakage
   opportunity sized from allowed dollars shows no benefit at all. The
   difference is in `plan_paid / allowed_amount` — 0.44 owned, 0.624 partner,
   0.80 out-of-network. Now dictionary rule **R6**, with a regression test.
2. **It corrected a metric denominator.** Our OR utilization used a 365-day
   year; ORs actually run ~270-290 days. Real utilization is **51.7-54.6%**,
   not 40.4-41.5%. The uniformity conclusion is unchanged (max/min 1.056), but
   the number was wrong in the dictionary and the analysis.
3. **It produced a new caveat we had missed.** Owned dollar share is uniform at
   61.3-62.4% in *every* city, so it carries no cross-market signal — markets
   must be ranked on geography. Now caveat **C6**, with a test.

**And it produced one wrong claim, which is why verification is not optional.**
The agent proposed that the "40%" figure came from dividing city volume by
*unfiltered* facility rows. Checked: that error makes Sacramento look ~28%
**higher** than Atlanta (10,308 vs 8,047 per clinic), not 40% lower. Refuted,
and pinned with a regression test so it cannot be re-adopted. A confident,
well-argued, plausible-sounding, wrong hypothesis is exactly the failure mode
this whole test architecture exists to catch — including when the agent is
right about everything else.

**The limitation we predicted was confirmed, unprompted.** The agent itself
flagged that `get_data_dictionary` embedded prior conclusions in its caveats
(C2b stated the Sacramento answer outright), so it "can't claim to have been
blind to the expected conclusion." That is the ADR's stated limitation, verified
from the inside.

## Discovery ablation — the caveat-free experiment, run

The limitation above was addressed rather than merely disclosed. C2b named the
market, the missing facility type and the leakage figure — the whole of Q1's
answer — in the file the agent is told to read before writing any SQL. C6 went
further than its own measurement and prescribed the geographic measures that
select that market.

**Both are now removed**, on this rule: *the dictionary may state measured
properties of the data; it may not state conclusions about the business
questions.* C1–C5 comply and stay. `test_dictionary_states_no_recommendation`
pins the rule; `evals/ablation.py` (`make ablation`) re-runs the experiment.

The experiment: strip every caveat block naming a market — which now removes
only C5's facility-counting example, leaving one market mention in the
hand-written layer (the org description, "Northern California, Greater Atlanta
and Central Texas", a fact about the company rather than a conclusion) — then
put the Q1 question to a fresh `claude -p` over real MCP stdio against the real
warehouse.

**All three runs reached the same recommendation — Sacramento, acute care,
surgery / cardiology / ED — in 14–18 turns each**, every one of them citing an
access measure rather than dollar share or absolute recapture. Recorded in
`evals/ablation.json`. One rejected the alternative ranking unprompted:

> Ranking markets by `recapture_plan_paid_musd` puts Atlanta ($39.5M) and San
> Antonio ($38.3M) first — but that ranking is almost perfectly collinear with
> market size, and both already have an owned hospital. It's a size artifact,
> not an opportunity signal. […] The genuine outlier is access.

That is the load-bearing step of `analysis/01_next_facility.md`, reconstructed
without the steer. Two things this does *not* license:

- **Three runs is a weak consensus measure.** 3/3 is consistent with a wide
  range of true rates. Quote it as "3 of 3 runs", never as "the agent always
  finds it"; raise `--runs` if the claim needs to carry more weight.
- **The marts still model `median_miles_to_acute` and `pct_acute_over_30mi`.**
  That is product design, not prompt staining — the same mart ships
  `recapture_plan_paid_musd`, which points at Atlanta. The ablated agent saw
  both and argued its way to the geographic one. Removing the columns would
  test a different product.

The ablation also surfaced a genuine gap the other direction: it treated
Sacramento / Stockton / Modesto as **one catchment**, which §3 of
`analysis/01_next_facility.md` disproves (Modesto sits 71.9 miles from a
Sacramento site). The corridor correction is analysis that was added, not
dictionary content restated — useful evidence the write-up is not a paraphrase
of its own semantic layer.

Test count went 81 -> 85. Remaining gap unchanged: **nothing has yet exercised
MCP stdio**, which still needs a human running `make serve` from a real client.

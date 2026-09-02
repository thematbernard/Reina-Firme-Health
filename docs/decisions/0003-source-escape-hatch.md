# ADR 0003 — Expose Redshift as an explicit tool, not as a fallback

- **Date:** 2026-09-01
- **Status:** Accepted (implemented: `query_source` in `mcp_server/server.py`)
- **Relates to:** [ADR 0002](0002-materialization-and-freshness.md), which
  explains why the marts exist at all

## Context

The marts answer the two strategy questions in one query each. Everything else
falls back to `raw.*` — 23 tables of full-history parquet, locally. But two
source tables are not in the local warehouse at all, by earlier decision:

| table | source rows | local |
|---|---|---|
| `outreach.communications_log` | 4,600,000 | **not extracted** |
| `ehr.observations` | 70,755,716 | pre-aggregated to 47,840,094 at patient × month × LOINC |

Both exclusions were justified for *facility siting*. Neither is justified for
"any question a strategy team might ask next," which is the whole point of
putting an LLM in front of the warehouse. A question about campaign response by
channel, or about row-level lab values, ended with the agent saying the data
does not exist — when it does exist, twelve feet away, behind credentials we
already hold.

Verified 2026-09-01 via `make check`: **21 of 21 extracted tables reconcile
exactly** to Redshift row counts. Source is reachable and correct; it was simply
not exposed.

## Decision

Add a fifth MCP tool, **`query_source(sql)`**, that queries Redshift directly.

**It is a separate tool, not a fallback inside `run_query`.** This is the
load-bearing part of the decision. The obvious design — if the local query
fails, silently retry at source — was rejected for three reasons:

1. **It inverts the correctness argument.** The marts make five measured caveats
   structurally impossible to express. At source, every one of them reverts to
   prose the model must remember: tables are not windowed to a common 12 months,
   `ops.appointments.provider_id` is exposed and is randomly assigned (C1),
   ownership is not pre-joined (C5). A silent fallback means the agent escapes
   the guardrails *precisely when it is struggling* — exactly when you least
   want it to.
2. **It hides a trade the reader needs to see.** A tool the agent must choose
   appears in the log as a deliberate decision, and the agent is instructed to
   say it used the hatch and why. A fallback appears as nothing at all.
3. **It puts a network dependency on the default path.** `run_query` reads a
   7 MB local file in ~2 ms and cannot fail. Redshift Serverless auto-pauses
   and a cold resume takes tens of seconds. That latency belongs on a path
   someone opted into.

Supporting choices:

- **`SOURCE_MAX_ROWS = 200`**, tighter than the local cap of 500 — this path is
  metered and slow, so it should be used for aggregates.
- **The same read-only and single-statement guardrails** as `run_query`, checked
  *before* any connection is opened (asserted by
  `test_query_source_guardrails_run_before_connecting`).
- **Results carry a banner** — `[SOURCE QUERY — mart caveats were NOT applied]`
  — so the provenance travels with the rows rather than living only in the
  tool's docstring.
- **Absent credentials, the tool fails fast** with a message telling the agent
  to fall back to `marts.*`/`raw.*`. It does not attempt a connection and stall
  the session. The portable marts-only deployment is unaffected.

## Connect with one retry

Redshift Serverless auto-pauses when idle, and the resume takes longer than a
short socket timeout allows. Measured 2026-09-01: `make check` with
`timeout=20` failed with `('connection time out', TimeoutError)`, and the
identical call succeeded on the next attempt — TCP to port 5439 was reachable
throughout, so this was never a network or whitelist problem.

Measured directly on 2026-09-01 with the new `make warm` target: a cold resume
took **24.0s**, and the next call **0.5s**. That is why `timeout=20` failed —
it was four seconds short. The number is worth recording, because "it timed out
once and worked the second time" is a guess about the cause and "24 seconds
against a 20-second timeout" is not.

`_connect_source` therefore uses `timeout=120` and retries **once**. One retry,
not a loop: a second timeout means something other than a cold start, and a
retry loop would turn a dead credential into a hung session.

The same fix was applied to the two existing Redshift callers, both of which
were short enough to fail on a cold workgroup:

| caller | was | now |
|---|---|---|
| `pipeline/00_connect_check.py` | 20s, no retry | 120s, one retry |
| `evals/query_path_benchmark.py` | 15s | 120s |

A retry inside the tool is the safety net, not the plan. `make warm` moves the
resume cost off the demo path entirely: one trivial query, run in pre-flight,
and it prints the elapsed time so the operator can see which state they got.

The benchmark one mattered: it produces the "0.4s at source" figure quoted in
ADR 0002 and on the impact slide, so an idle workgroup made a published number
unreproducible on demand.

## Consequences

**The correctness guarantee now has three tiers, and they should be named as
such rather than blurred:**

| tier | caveats | guarantee |
|---|---|---|
| `marts.*` | 5 encoded structurally | strongest — the wrong answer is not expressible |
| `raw.*` | prose in the dictionary | the model must obey rules correctly, every query |
| `query_source` | prose, plus no local reconciliation | weakest — and now explicitly labelled |

This *widens* the ungoverned surface, which is a real cost. The mitigation is
that the widening is opt-in, logged, labelled in the returned rows, and
described in a docstring that a test asserts still contains the warning
(`test_query_source_description_warns_that_caveats_do_not_apply`).

**It also strengthens the honest version of the scope limitation.** Previously:
"anything the marts do not carry drops to `raw.*`, and two tables are simply
unavailable." Now: "there are three tiers, the agent picks one and tells you
which, and the guarantee attached to each is documented."

**What this does not do:** it does not govern the source path. `marts.member_360`
(roadmap item 3) is still the right answer for the `raw.*` tier, and nothing
equivalent exists for source. A curated tool per question — roadmap item 5 —
would narrow this further by giving the agent a right answer to reach for
before it reaches for raw SQL against production.

## Alternatives rejected

- **Silent fallback in `run_query`** — see the three reasons above.
- **Extract the two missing tables locally.** `communications_log` is 4.6M rows
  and `ehr.observations` is 70.8M at row grain; the second is the extract that
  already "did not pay for itself" once. Extracting both to serve hypothetical
  questions is speculative work, and the whole point of an escape hatch is to
  avoid guessing which tables a future question needs.
- **Leave it closed and answer "unavailable."** Defensible for the two questions
  asked. Indefensible for an interface whose stated value is the *next* question.

# Technical write-up — Reina Firme Strategy Engine

Problem 3: *"The Strategy team can't get answers fast enough."* Both questions
are answered, and one of them turned out to be wrong.

This is the 1–3 page write-up the brief asks for: architecture, key decisions
and tradeoffs, assumptions, and what I would build next. Everything here is
expanded elsewhere — the [README](../README.md) for how to run it,
[docs/verified-status.md](verified-status.md) for method behind every measured
number, [analysis/](../analysis) for the two answers in full, and
[docs/decisions/](decisions) for the ADRs.

## The answers, first

**Where should we open the next clinic?** Not a clinic. Open in **Sacramento, as
an acute-care hospital** — ~110 beds and 6–8 ORs, built for surgery,
cardiology and an emergency department. Sacramento has 50,639 active members and
**zero owned hospitals, zero owned urgent cares**. Its members travel a median
**75.5 miles** for acute care against Atlanta's 9.1, and 95.7% of acute claims
are served more than 30 miles from home. The ambulatory need is already met:
imaging, primary care, labs and behavioral are ~72% served locally, while the
hospital lines run ~12%. Oakland also has no owned hospital but sits 12.6 miles
from owned capacity in San Francisco and Fremont — Sacramento has no fallback,
and that column is the decision.

**Why is Sacramento utilization 40% below Atlanta?** It isn't. Across all 64
owned clinics the coefficient of variation in completed appointments is
**0.68%**, and the widest max/min ratio is **1.029**. A 40% gap needs ~1.67, so
it is not constructible from this data. The two clinics with the closest
attributed panels (11,190 vs 11,174) differ by **0.4%**. Three of four
denominators put Sacramento *above* Atlanta — per panel member it is **+27.9%**.
The real finding is the denominator trap: throughput barely moves, so whichever
denominator you pick manufactures the story.

## Architecture

    Redshift (read-only)
      └─ extract to parquet ─→ DuckDB warehouse ─→ 4 marts
                                                    └─ semantic layer
                                                         └─ MCP server (4 tools)
                                                              └─ Claude

A **mart** here is a table modelled for a question rather than for a source
system: a fixed grain with joins and business rules already applied.

| mart | grain | retires |
|---|---|---|
| `facility_metrics` | one row per facility (284) | the `provider_id` denominator trap; the OR-utilization denominator |
| `market_summary` | one row per market (42) | mixed time windows; partner facilities in the denominator |
| `market_flows` | member_city × care_city × service_line × network_status (12.4K) | service-line spend needing a three-table join; multi-city catchments |
| `identity_xwalk` | patient_id ↔ member_id (592K) | the absence of a shared key between EHR and payer |

The semantic layer is two documents in one: hand-written business rules, and a
schema reference **generated** from the warehouse so column facts cannot drift
from reality. The MCP server exposes four tools over stdio, read-only and
row-capped, and reports a build fingerprint in its instructions so a client can
detect that it is running a stale server.

## Key decisions and tradeoffs

**Materialize locally rather than query source.** Source access is read-only
(the brief: *"You'll be given read-only credentials"*), so no view or mart can
live at source. That makes a local warehouse the only place correctness rules
can be *encoded* rather than merely documented — see
[ADR 0002](decisions/0002-materialization-and-freshness.md). Tradeoff: freshness
becomes an operational concern. Mitigated by measurement — claims are not final
in source until a median **67 days** after service, so a nightly refresh adds
≤24h to an inherent 67-day pipeline. `marts._build_metadata` makes freshness
observable, and the mart swap is atomic. The scheduler is specified, not built.

**Make wrong answers unreachable instead of documented.**
`ops_appointments.provider_id` is randomly assigned — 1.2% agreement with the
provider's own facility, against 1.19% expected by chance. An agent using it as
a staffing denominator reports ~5,597 providers at every clinic. Rather than
write "don't use this column," the marts source provider counts correctly and
never expose the bad one. Five documented caveats moved from *a rule the agent
must remember* to *impossible to express*. Tradeoff: **the guarantee stops at
the mart edge.** Off-mart questions fall back to `raw.*`, where caveats revert
to prose — and that is exactly where the one real eval failure happened.

**Test the data and the agent separately.** `make test` runs **157**
deterministic tests in ~16s with no AI involved: mart grain, reconciliation back
to source, and guards that retired caveats have not crept back. Several tests
pin the *conclusions* of this write-up, including one asserting that recapture
dollars alone would pick Atlanta rather than Sacramento — so the narrative
cannot quietly drift into a stronger claim than the data supports. Separately,
11 eval cases measure whether the agent reaches the right conclusion through the
tools: **9/11**, with both bad-premise and both unanswerable cases passing.

**Report failures rather than tune the tests.** Of the two eval failures, one is
real (the off-mart raw path, numbers ~8% low from an undisclosed enrollment
filter) and one is a grader artifact — the agent named the trap it avoided, and
a substring check scored that identically to falling into it. Fixing the check
would have shown 10/11. It is left unfixed, because a number obtained by
adjusting a test after it fails is not a measurement.

**No dbt.** For four marts and one `make` target it adds a dependency without
changing the output. A deliberate non-choice; revisit at ten marts or multiple
contributors.

## Assumptions

1. **The brief's stated figures do not match the warehouse, and I used the
   warehouse.** The brief describes ~3M members (data: 1,100,000 member records,
   one row per member, full table, no filter); owned care costing ~35%/~60% less
   than in-network/out-of-network (measured: **29.5%** and **45.0%**); and ORs at
   ~62% utilization (measured: **51.7–54.6%** on operating days). Every number
   here is internally consistent with the data. This makes the $33.2M
   opportunity conservative relative to the brief's own economics.
2. **A "market" is a city, and a *catchment* is not a market.** Marts key both
   member population and facility footprint on city so supply and demand are
   comparable. Catchment is measured separately, by distance: 100% of Sacramento
   members sit within 45 miles of the proposed site, 32% of Stockton, and **0% of
   Modesto (median 71.9 miles)**. The three-market region is a $33.2M
   opportunity; the *building* serves ~60,500 members and ~$19.7M of it. An
   earlier draft conflated the two and oversized the facility by roughly 2x.
3. **Distances are straight-line (haversine), not drive time.** 252 isochrone
   polygons in `external.drive_time_isochrones` are unused. This almost
   certainly *understates* Sacramento's disadvantage, so measuring it should
   strengthen the recommendation.
4. **$33.2M assumes full recapture** at current owned cost ratios, across all
   three markets. It is a ceiling on the regional case, not a forecast, and not
   the single-facility figure (~$19.7M).
5. **The dataset is near-uniform synthetic data.** CV 0.68% across 64 clinics
   means no facility-level *performance* question is answerable here. That is a
   property of the data, not a modelling choice — and it is the reason question
   two has no gap to explain.
6. **Scope: demand side only.** No capital cost, staffing, licensure or
   certificate-of-need analysis.
7. **Two source deviations, both deliberate.** `outreach.communications_log`
   (4.6M rows) was skipped as out of scope for a siting decision, and
   `ehr.observations` (47.8M rows) was extracted pre-aggregated, so row-level
   vitals and labs are not queryable.

## What I would build next, given another week

1. **Nightly refresh scheduler** — decided and specified (ADR 0002); only the
   cron/Airflow wiring is outstanding. Deltas must key on the *landing* column,
   never the event date, or late-arriving claims are dropped permanently.
2. **DOB-variant identity fix** — recall collapses to **3.6%** on a transposed
   date of birth, and it is the only corruption that produces *wrong* links
   rather than missing ones (29 of 138 matches wrong). This is the one item that
   is actively dangerous rather than merely absent.
3. **`marts.member_360`** — the crosswalk has no consumer today; it is only ever
   a join hop. This is also what would govern the raw path where the one real
   eval failure occurred.
4. **Close out the evals** — `--reps 3` for a variance figure, and
   negation-aware grading to fix the false positive honestly.
5. **Curated MCP tools** — `compare_facilities`, `market_summary(city)`, with
   raw SQL kept as the escape hatch.
6. **Real drive time** — replace haversine with the isochrones.

## Tools used

Built with **Claude Code** (Claude Opus 5) as the primary development
environment — pipeline and mart SQL, tests, the MCP server, and documentation
drafting, all reviewed and corrected by hand. Stack: Python, DuckDB, PyArrow,
`psycopg`/`psql` against Redshift, `pytest`, `uv`, and the Model Context Protocol
Python SDK. The eval harness drives the `claude -p` CLI over the real stdio MCP
transport, so the same tooling appears in the product and in its tests.

**Time spent: approximately 9–10 hours** across three sessions, against a
planned budget of 8–10. Per-session breakdown in the
[README](../README.md#time-spent).

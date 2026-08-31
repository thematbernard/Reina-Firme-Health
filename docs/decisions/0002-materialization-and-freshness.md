# ADR 0002 — Materialize a local warehouse, refresh it nightly

- **Date:** 2026-08-29
- **Status:** Accepted (nightly job specified, not yet implemented — see Roadmap)
- **Supersedes:** the "freshness is bounded by the last extract" caveat in
  `docs/verified-status.md`, which framed a deliberate decision as a limitation

## Context

Source access is **read-only Redshift** — the assignment states it directly:
*"You'll be given read-only credentials at the start of your assessment
window."* We cannot create tables, views, or marts there, so any consistent
shape has to live somewhere we control.

Measured, on the three questions in `evals/query_path_benchmark.py`:

| path | all 3 questions |
|---|---|
| `marts.*` in DuckDB | **2ms** |
| hand-assembled joins in DuckDB | 298ms |
| the same SQL against Redshift | 0.4s |

Redshift at 0.1–0.2s per query is **not slow**, and we should not pretend
otherwise. The reason to materialize is not raw latency — it is that a
materialized mart is the only place we can *encode the correctness rules*.
Five documented traps (randomly-assigned `provider_id`, mismatched time
windows, partner facilities in the denominator, the OR denominator, savings
hidden in `allowed_amount` instead of `plan_paid`) became structurally
impossible once the shape was ours to define. Against read-only source, they
would have remained prose in a dictionary that an agent has to obey correctly
on every single query.

## Decision

Materialize a local DuckDB warehouse — parquet snapshot of source plus
materialized marts — and **refresh it on a nightly schedule** so each morning
starts on current data.

### Why nightly is the right cadence, measured

Claims are not present in source as final adjudicated rows until long after
care is delivered:

| service_date → processed_date | days |
|---|---|
| median | **67** |
| p90 | 91 |
| max | 104 |

(Split: ~7 days to submit, ~60 to adjudicate.)

A nightly refresh therefore adds **≤24 hours on top of an inherent ~67-day
pipeline — roughly 0.5% of the latency already in the data.** For strategy
questions, where the decision cycle is weeks and the underlying question is
"where should we open a facility," that is immaterial. Sub-daily refresh would
add cost and operational surface to chase 0.5% of a number nobody can act on
faster.

### Shape of the nightly job

1. **Incremental extract keyed on the landing column, never the event column.**
   This is the detail that would quietly corrupt the warehouse if missed:
   because claims arrive a median 67 days after service, a delta filtered on
   `service_date` would **permanently drop every late-arriving claim**. Deltas
   must filter on `processed_date` / `submitted_date` / `booked_at` /
   `updated_at`. `marts._build_metadata.incremental_column` records the right
   column per table, and a test asserts claims use `processed_date`.
2. **Restate a rolling lookback window** rather than appending only. With p90
   lag at 91 days, re-pull the trailing ~100 days each night and replace that
   partition. Adjudicated amounts also get restated, so append-only would
   accumulate stale dollars.
3. **Rebuild marts in full every night.** The whole mart layer builds in
   **1.36s**, so incrementalizing it would add complexity for no gain.
4. **Swap atomically.** DuckDB permits a single writer, so an in-place rebuild
   would either fail against a live MCP server or expose a half-built
   warehouse. `04_build_marts.py` builds to `warehouse.duckdb.tmp` and
   `Path.replace()`s it in — atomic on POSIX, so readers see the old or the new
   file, never a partial one.
5. **Record and monitor provenance.** `marts._build_metadata` carries
   `built_at`, per-source `row_count`, `max_event_date`, and
   `days_behind_today`. Alert when `built_at` is older than ~26 hours: a cache
   whose staleness is invisible is worse than no cache, because nobody
   re-derives the number to catch it.

Nightly delta volume is small — roughly 14K claims, 8K encounters, 9K
appointments and 10K rx fills per day, against a 17M-row, 1.6GB snapshot. The
initial full extract took ~1 hour; nightly deltas are a seconds-to-minutes job.

### What we would deliberately NOT put on this path

Anything needing intraday truth: live bed capacity, day-of OR scheduling,
same-day appointment availability. Those are operational questions, not
strategy questions, and they should query source directly rather than degrade
this path's simplicity to serve them.

## Consequences

- **Positive, and initially unintended:** the source ops tables only hold ~12
  months (`ops_appointments` covers 2025-06 → 2026-05). If that is a rolling
  window at source, the snapshot *preserves history the source discards*. That
  is an argument for materializing beyond query speed.
- Freshness becomes an operational concern with a failure mode (silent staleness)
  that did not exist when queries hit source directly. Mitigated by
  `_build_metadata` + alerting, which is why that table exists.
- Snapshot storage grows with history; currently 1.6GB parquet for 3 years.
- The `raw.*` views still expose the full 3-year claims history for anything the
  pre-windowed marts do not carry.

## Revisit if

- Write access to a warehouse (Redshift, Snowflake, etc.) becomes available →
  build the marts there instead and delete the snapshot; the mart SQL ports
  largely unchanged, and this whole ADR becomes unnecessary.
- Claims adjudication lag drops materially → shorten the lookback window
  (`test_claims_incremental_key_is_not_the_event_date` fails if the lag
  collapses below 30 days, which is the prompt to revisit).
- A genuine intraday use case arrives → give it a separate path, do not
  accelerate this one.

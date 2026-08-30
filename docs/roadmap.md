# Additional work

Ordered by value, with what is already true stated plainly so nothing here reads
as more finished than it is. "Measured" items have a `make` target.

## 1. Nightly refresh job — specified, not implemented

**Decision recorded in [ADR 0002](decisions/0002-materialization-and-freshness.md).**

The warehouse is a deliberate materialized cache of read-only Redshift: it is
the only place we can encode the correctness rules, since we cannot create
objects at source. The remaining work is to put it on a schedule so each morning
starts on current data.

What exists today:

- `make build` (extract → marts → docs) runs the whole refresh by hand
- mart rebuild is **1.06s**, so no incrementalization is needed there
- the swap is already atomic (build to `.tmp`, `Path.replace()`), so a refresh
  cannot corrupt a live reader
- `marts._build_metadata` records `built_at`, per-source row counts,
  `max_event_date`, `days_behind_today`, and the correct incremental column

What is left:

| task | note |
|---|---|
| Scheduler | cron / Airflow / GitHub Actions — nightly, off-peak |
| Incremental extract | key on the **landing** column (`processed_date`, `booked_at`, `updated_at`), never the event date — claims arrive a median 67 days after service, so a `service_date` delta silently drops late arrivals |
| Rolling restatement | re-pull trailing ~100 days (p90 lag is 91) and replace the partition; adjudicated amounts get restated, so append-only accumulates stale dollars |
| Staleness alert | page when `built_at` is older than ~26h; silent staleness is the failure mode this whole design introduces |
| Extract retry/resume | `02_extract.py` already skips existing files and reconnects on failure; needs a per-table success ledger |

Why nightly and not faster: measured median claims lag is **67 days**
(p90 91, max 104), so nightly adds ~0.5% to latency already in the data.
Sub-daily refresh would buy nothing actionable. Operational questions needing
intraday truth (live bed capacity, day-of OR scheduling) should query source
directly rather than complicate this path.

## 2. Close the identity recall gaps — measured, fix designed

`make identity-quality`. Precision is ~99.89% overall (~85.2% on the fuzzy
tier, three independent estimators agreeing within 0.2pp). Recall is uneven:

| corruption | recall | wrong links |
|---|---|---|
| firstname_typo / zip_missing | 100% | 0 |
| lastname_typo | 61.4% | 0 |
| married_name | 54.9% | 0 |
| typo + missing zip | 10.1% | 0 |
| **dob_day_transposed** | **3.6%** | **29** |

Two fixes, in priority order:

1. **DOB-variant blocking pass.** This is the only failure mode that produces
   *wrong* links rather than missing ones — 29 of 138 matches (21%) were wrong,
   because fuzzy blocks on exact DOB and a transposed birthday sends the matcher
   hunting among people born on a different day. Block on DOB variants
   (transpositions, ±1 day, swapped month/day) and require a higher similarity
   threshold when surname *and* zip both disagree. Converts a dangerous failure
   into a safe one.
2. **Surname-change recovery.** 61.4% / 54.9% is a direct consequence of the
   fuzzy gate requiring *exact surname OR matching zip*, and zip agrees for only
   56.2% of exact matches. Add address-line or phone/email as an alternative
   corroborating key — they are in `payer_members` and currently unused, which is
   also why they work as the precision estimator.
3. **Hand-grade ~50 fuzzy links** so precision is a graded sample, not only an
   estimator.

## 3. `marts.member_360` — not built

Unified identity currently has **no consumer**: the crosswalk is only ever a
join hop. One row per member (demographics, plan, employer, geography, PCP
facility, program enrollments, and `patient_id`) is the payoff, and it is cheap
now that the mart pattern is established.

## 4. MCP stdio — done, with one residual

Covered by `tests/test_stdio.py` (14 tests, negative-controlled) and the
server's build fingerprint. See
[verified-status §4](verified-status.md#4-mcp-transport--measured).

The residual is operational, not testable: a client that started the server
before a change keeps running the old code for the whole session. The
fingerprint makes that visible (`make fingerprint` vs the `[build ...]` tag in
the server's instructions) but does not prevent it. A supervisor that restarts
the server when `server.py` or the semantic layer changes would close it.

## 5. Run the agent evals — harness ready, never executed

`evals/run.py` (11 cases: 2 factual, 5 analytical, 2 bad-premise, 2
unanswerable) has never run — no Anthropic credential is configured here.
Export a key and `make evals`, then `--reps 3` for variance. Report the failures
rather than tuning cases until they pass.

Related: re-run the cold-agent probe now that the marts exist. It needed **29
tool calls** against `raw.*`; the marts should cut that sharply, and tool-call
count is the honest proxy for time-to-answer.

## 6. Curated MCP tools

`run_query` is maximally flexible and maximally risky. Now that
`facility_metrics` and `market_summary` exist, `compare_facilities(a, b)` and
`market_summary(city)` would make the common paths impossible to get wrong,
leaving raw SQL as the escape hatch.

## 7. Real drive time

Distances are straight-line haversine. `raw.external_drive_time_isochrones`
holds 252 precomputed polygons and is unused. Sacramento's 75.5-mile median is
almost certainly *worse* in drive time, so this strengthens the Q1 case rather
than threatening it — but it should be measured, not assumed.

## 8. Things deliberately not done

- **`mart_encounters` / `mart_claims`** — a 17M-row enriched claims mart would
  add build time and storage for questions the two existing marts already
  answer. Revisit when a question needs claim-line grain.
- **dbt** — worth it for a team and a lineage graph; for four marts and one
  `make` target it would add a dependency without changing the output.
- **Chasing the source's near-uniform synthetic data** — per-facility volume has
  CV 0.68%, so no facility-level performance question is answerable here. That
  is a property of the dataset, documented in caveat C2, not something to model
  around.

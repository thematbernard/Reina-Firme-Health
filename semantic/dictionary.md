# Reina Firme Health — Semantic Layer

Hand-written business semantics for the local DuckDB warehouse
(`data/warehouse.duckdb`, extracted 2026-08-28).

**Column lists and date ranges are NOT in this file.** They live in
`semantic/schema.md`, which is generated from the warehouse by `make docs`.
Never trust a remembered column name — check `schema.md` or call
`describe_table`. (An earlier hand-written version of this file claimed
`ops_facilities.name` and `ops_appointments.patient_id`; neither exists, and
the agent emitted broken SQL because it believed them.)

Reina Firme is an integrated payer + provider: 1.1M members, care delivered at
84 owned facilities (8 hospitals, 64 clinics, 12 urgent cares) across Northern
California, Greater Atlanta and Central Texas, plus ~200 partner facilities.

## Critical rules — read before writing SQL

**R1. Two identity systems, and only some tables need the crosswalk.**
`payer.*` tables key on `member_id`; `ehr.*` tables key on `patient_id`. There
is no shared key in the source. To join *EHR to payer*, go through
`marts.identity_xwalk` (591,712 links = 87% of the 680K patients).
**But `raw.ops_*` tables key on `member_id`, not `patient_id`** — appointments,
referrals, or_schedule and bed_census join straight to `payer.*` with no
crosswalk. Using the crosswalk where it isn't needed silently drops the 13% of
patients that never matched.

**R2. Time windows differ by table — window both sides of any comparison.**
Claims / encounters / procedures / rx: 2023-06 → 2026-05 (3 years).
Ops tables (appointments, referrals, or_schedule, bed_census_daily):
2025-06 → 2026-05 (1 year **only**).
`ehr_conditions.onset_date` stops at 2023-06 — there are no condition onsets
during the ops window at all. Per-column observed ranges are in `schema.md`.

**R3. Owned vs partner.** `raw.ops_facilities.ownership` ∈ {`owned`,`partner`}.
The table holds **all 284** facilities. Any "our network" metric must filter
`ownership='owned'`, or partner sites inflate the denominator (see C5).
Owned care costs ~35% less than partner and ~60% less than out-of-network.

**R4. Leakage** = volume or dollars going to `ownership='partner'` (or
out-of-network per `payer_claims.network_status`) for a service the owned
network offers in that market. Compare like to like: check
`ops_facilities.service_lines` before calling something leakage.

**R5. Cost columns are not interchangeable.** `payer_claims` carries
`billed_amount`, `allowed_amount`, `plan_paid` and `member_paid`. Use
`allowed_amount` for economic volume and `plan_paid` for Reina Firme's own
cost. Never sum `billed_amount` — it is list price, not money that moved.

## Metric definitions (canonical — do not invent alternatives)

**Facility utilization** has a different valid denominator per facility type.
There is no single utilization column.

- **Operating rooms** (hospitals): booked minutes ÷ available minutes.
  Booked = `date_diff('minute', scheduled_start_dt_local, scheduled_end_dt_local)`
  from `raw.ops_or_schedule` — there is no pre-computed minutes column.
  Available = distinct `or_room` per facility × operating days × staffed hours.
  Exclude cancellations: `actual_start_dt_local IS NULL` marks the ~13% of
  cases that never ran.
- **Inpatient beds** (hospitals): `occupied_beds_midnight` ÷ `total_beds` from
  `raw.ops_bed_census_daily`.
- **Clinics**: completed appointments (`status='completed'`) from
  `raw.ops_appointments`. Clinics have NULL `total_beds`/`total_ors`, so there
  is no capacity column. Valid denominators are providers **based** at the
  facility (`ops_providers.primary_facility_id`), attributed panel
  (`payer_members.primary_pcp_provider_id` → provider → facility), or
  drive-time population. **Never normalize by
  `count(DISTINCT ops_appointments.provider_id)` — see C1.**

**Appointment status** ∈ {`completed`, `booked`, `no_show`,
`cancelled_by_patient`, `cancelled_by_provider`}. `booked` includes future
appointments, so a raw completion rate is diluted by the window's tail; filter
`scheduled_dt_local < current_date` for a realized rate.

**Eligible member months**: from `raw.payer_member_eligibility_history`
between `effective_date` and `end_date` (`end_date IS NULL`, 96% of rows, =
still covered). Use this as the denominator for any per-member rate — member
counts alone ignore partial-year coverage.

## Data-quality caveats (measured, not assumed)

These were found by testing the warehouse. Each one will silently produce a
wrong answer if ignored.

**C1. `ops_appointments.provider_id` is randomly assigned — do not use it.**
Only **1.2%** of appointments have a provider whose `primary_facility_id`
matches the appointment's facility; chance alone gives ~1.2% across 84
facilities. Every clinic therefore shows ~5,597 "distinct providers" (of 14,000
total). This column cannot support provider productivity, staffing, panel or
capacity analysis. `ops_providers.primary_facility_id` is the real
provider↔facility assignment.

**C2. Per-facility volume is near-uniform, so large utilization gaps are not
constructible.** Completed appointments across all 64 owned clinics: mean
18,038, sd 122, CV **0.68%**, max/min **1.029**. EHR encounters agree
independently (CV 1.27%, max/min 1.068). OR utilization spans 40.4-41.5% across
the 8 hospitals; bed occupancy 54.1-55.4%. The widest gap between any two
facilities on any volume measure is under 7%.

Consequence: **if asked to explain a 40% utilization gap, do not manufacture
one.** Report that the premise does not reconcile. Any large gap you can
produce comes from the denominator, not the numerator — panel-normalized
utilization has a 3.18x spread purely because panel size varies while
throughput does not. See `analysis/02_sacramento_vs_atlanta.md`.

**C2b. Sacramento vs Atlanta specifically.** Size-matched clinics differ by
0.4%, and Sacramento sits at or above Atlanta on every normalized measure. The
real Sacramento finding is network composition: 55,183 members, zero owned
hospital and zero owned urgent care, 92.8% of hospital claims leaving the
market, $228M/yr of allowed spend going out of market vs Atlanta's 31%.

**C3. Future-dated rows exist.** `payer_members.dob` and `enrollment_date`
extend to 2026-12-28, and `termination_date`/`eligibility.end_date` to 2030.
Filter on `current_date` when computing age or active enrollment.

**C4. Referral funnels are mostly incomplete.** `ops_referrals.scheduled_dt`
is 50% null and `completed_dt` 75% null. Treat these as funnel stages, not
missing data: ~25% of referrals complete. `referred_to_facility_id` is 22%
null (not directed to an in-network facility).

**C5. Facility counts must filter `ownership`.** Sacramento has 4 owned
clinics but 7 rows in `ops_facilities`; Atlanta 8 owned but 18 rows. Counting
facilities per city without `ownership='owned'` inflates the owned footprint by
2–3x and understates per-facility volume by the same factor.

## Where to look things up

- **Columns, types, row counts, date ranges** → `semantic/schema.md` (generated)
- **Join paths** → `semantic/joins.json`, rendered with measured orphan counts
  into `schema.md`. All 24 paths are asserted orphan-free by
  `tests/test_warehouse.py`.
- **Identity matching logic** → `pipeline/sql/01_identity_xwalk.sql`
  (`match_method` ∈ exact / exact_tiebreak / fuzzy; fuzzy is 4,537 links at
  Jaro-Winkler ≥ 0.92 and is the least trustworthy slice).
- **Geography**: members and facilities both carry lat/long;
  `external_census_tract_demographics` keys on `census_tract_geoid` with
  `polygon_wkt`; `external_drive_time_isochrones` has 252 precomputed polygons
  (isochrone_minutes per facility).

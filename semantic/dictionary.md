# Reina Firme Health — Data Dictionary & Semantic Layer

Local DuckDB snapshot of Reina Firme's warehouse (extracted 2026-08-28).
Reina Firme is an integrated payer + provider: ~1.1M members, care delivered at
84 owned facilities (8 hospitals, 64 clinics, 12 urgent cares) in Northern
California, Greater Atlanta, and Central Texas, plus ~200 partner facilities.

## Critical rules — read before writing SQL

1. **Two identity systems.** `payer.*` tables key on `member_id`; `ehr.*` tables key on
   `patient_id`. There is NO shared key in the source data. To join across them, ALWAYS
   go through `marts.identity_xwalk` (patient_id ↔ member_id, 87% of patients linked,
   `match_method` in: exact, exact_tiebreak, fuzzy).
2. **Time windows differ by table.** Claims/encounters/procedures/rx: June 2023 – May 2026.
   Ops tables (appointments, referrals, or_schedule, bed_census_daily): June 2025 – May 2026 ONLY.
   Never compare a 3-year table against a 1-year table without windowing both to the same range.
3. **Owned vs partner.** `raw.ops_facilities.ownership` ∈ {'owned','partner'}. Care at owned
   facilities costs ~35% less than partner, ~60% less than out-of-network. Volume sent to
   partners when an owned facility could serve it is called **leakage**.
4. Table names here use the local layout: `raw.<sourceschema>_<table>` (views over parquet)
   and `marts.<table>` (derived). E.g. Redshift's `payer.claims` is `raw.payer_claims`.

## Metric definitions (canonical — do not invent alternatives)

- **Utilization (facility):** actual volume / capacity for a period.
  For ORs: booked minutes / available minutes from `raw.ops_or_schedule`.
  For clinics: completed appointments from `raw.ops_appointments` (status column) per facility,
  optionally normalized by provider count or rooms.
- **Leakage rate:** share of encounters/claims volume (or dollars) at `ownership='partner'`
  facilities out of total in-network volume, for services the owned network offers.
- **Eligible member months:** from `raw.payer_member_eligibility_history` between
  effective_date and termination-equivalent end.

## Tables

### raw.payer_members (1.1M rows) — one row per insured member
member_id, name, dob, gender, address + lat/long, phones, email, preferred_language,
sms_consent, TCPA window, primary_pcp_provider_id, plan_id, employer_id,
enrollment_channel/date, termination_date (NULL = active).

### raw.payer_claims (17.1M) — paid claims, service_date 2023-06→2026-05
member_id, claim/line ids, service_date, facility_id, provider_id, place_of_service,
cpt/diagnosis codes, service_line, allowed/paid amounts, network_status.

### raw.payer_plans (42), raw.payer_employers (820), raw.payer_member_eligibility_history (1.5M)
Plan metadata (LOB: employer group vs ACA), employer groups, coverage spans.

### raw.ehr_patients (680K) — one row per patient in the EHR (owned-facility care)
patient_id, mrn, name, dob, gender, address, primary_provider_id.

### raw.ehr_encounters (9.0M) — EHR visits at owned facilities, 2023-06→2026-05
patient_id, encounter_id, facility_id, provider_id, encounter_type, admission/discharge dt,
department/service line fields.

### raw.ehr_conditions (719K), raw.ehr_medications (575K), raw.ehr_procedures (6.1M)
Diagnoses (onset 2019–2023), meds, procedures (CPT) performed at owned facilities.

### raw.ehr_observations_monthly (47.8M) — AGGREGATED labs/vitals
patient_id × month × LOINC: n_observations, avg_value_numeric, n_abnormal.
(Raw 70M-row observations table was aggregated during extraction.)

### raw.ops_facilities (284) — ALL facilities, owned and partner
facility_id, name, facility_type (hospital/clinic/urgent_care/ambulatory_surgery/imaging),
ownership (owned/partner), address, lat/long, service_lines (delimited string),
total_beds, total_ors, cost_index.

### raw.ops_providers (14K) — providers with specialty, employment (owned vs partner network)

### raw.ops_referrals (1.2M) — referrals written, 2025-06→2026-05
referral_id, member_id, referring_provider_id, referred_to_provider_id,
referred_to_facility_id, specialty, status, issued/scheduled/completed dt, urgency.

### raw.ops_appointments (3.2M) — appointments at owned facilities, 2025-06→2026-05
facility_id, provider_id, patient_id, scheduled_dt_local, status (incl. no-shows/cancellations),
appointment/visit type.

### raw.ops_or_schedule (83K) — OR cases at owned hospitals, 2025-06→2026-05
facility_id, or room, surgeon_id, scheduled/actual start-end, case type, status
(incl. cancellations), booked minutes.

### raw.ops_bed_census_daily (18K) — daily census per owned hospital, 2025-06→2026-06

### raw.outreach_wellness_programs (6) — the six wellness programs
### raw.outreach_program_enrollments (88K) — member_id, program_id, enrollment_dt, status

### raw.external_census_tract_demographics (24K) — tract-level population, age/income mix
### raw.external_competitor_facilities (2.8K) — non-Reina-Firme facilities with lat/long
### raw.external_drive_time_isochrones (252) — precomputed drive-time polygons per facility

### raw.pharmacy_rx_claims (11.0M) — fills 2023-06→2026-05: member_id, ndc, prescriber_id, costs

### marts.identity_xwalk (592K) — patient_id ↔ member_id linkage (see rule 1)

## Common join paths
- claims → members: `raw.payer_claims.member_id = raw.payer_members.member_id`
- claims → facilities: `raw.payer_claims.facility_id = raw.ops_facilities.facility_id`
- encounters → facilities: `raw.ehr_encounters.facility_id = raw.ops_facilities.facility_id`
- EHR ↔ payer: `ehr.patient_id → marts.identity_xwalk → payer.member_id`
- referrals → destination: `raw.ops_referrals.referred_to_facility_id = ops_facilities.facility_id`
- geography: members have lat/long and zip; facilities have lat/long;
  `raw.external_census_tract_demographics` keys on census tract.

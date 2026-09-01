# Reina Firme — Schema Reference (GENERATED)

**Do not edit by hand.** Regenerate with `make docs`
(`pipeline/05_gen_schema_doc.py`). `tests/test_warehouse.py` fails if this
file is stale, so the column lists below always match the warehouse.

Business meaning, metric definitions and data-quality caveats are in
`semantic/dictionary.md` — read that first.

Local naming: Redshift's `payer.claims` is `raw.payer_claims`
(`raw.<source_schema>_<table>`); derived tables are `marts.<table>`.

## Tables

### raw.ehr_conditions — 718,896 rows (719K)

| column | type | notes |
|---|---|---|
| `condition_id` | BIGINT |  |
| `patient_id` | VARCHAR |  |
| `icd10_code` | VARCHAR |  |
| `condition_name` | VARCHAR |  |
| `onset_date` | DATE | range 2019-06-02 → 2023-06-01 |
| `resolved_date` | DATE | range 2019-08-03 → 2025-01-19; 90% null |
| `status` | VARCHAR |  |

### raw.ehr_encounters — 9,005,376 rows (9.0M)

| column | type | notes |
|---|---|---|
| `encounter_id` | VARCHAR |  |
| `patient_id` | VARCHAR |  |
| `facility_id` | VARCHAR |  |
| `provider_id` | VARCHAR |  |
| `encounter_class` | VARCHAR |  |
| `admission_dt` | TIMESTAMP | range 2023-06-01 → 2026-05-31 |
| `discharge_dt` | TIMESTAMP | range 2023-06-01 → 2026-06-14 |
| `length_of_stay_days` | DECIMAL(3,1) |  |
| `primary_dx_code` | VARCHAR |  |
| `chief_complaint` | VARCHAR |  |

### raw.ehr_medications — 574,941 rows (575K)

| column | type | notes |
|---|---|---|
| `medication_id` | BIGINT |  |
| `patient_id` | VARCHAR |  |
| `rxnorm_code` | VARCHAR |  |
| `medication_name` | VARCHAR |  |
| `dose` | VARCHAR |  |
| `start_date` | DATE | range 2020-06-01 → 2023-06-01 |
| `end_date` | DATE | range 2020-08-01 → 2025-08-08; 75% null |
| `prescriber_id` | VARCHAR |  |

### raw.ehr_observations_monthly — 47,840,094 rows (47.8M)

| column | type | notes |
|---|---|---|
| `patient_id` | VARCHAR |  |
| `observation_month` | DATE | range 2023-06-01 → 2026-06-01 |
| `observation_loinc` | VARCHAR |  |
| `observation_name` | VARCHAR |  |
| `n_observations` | BIGINT |  |
| `avg_value_numeric` | DECIMAL(7,4) |  |
| `n_abnormal` | BIGINT |  |

### raw.ehr_patients — 680,000 rows (680K)

| column | type | notes |
|---|---|---|
| `patient_id` | VARCHAR |  |
| `mrn` | VARCHAR |  |
| `first_name` | VARCHAR |  |
| `last_name` | VARCHAR |  |
| `dob` | DATE | range 1936-01-01 → 2026-12-28 |
| `gender` | VARCHAR |  |
| `address_line1` | VARCHAR |  |
| `city` | VARCHAR |  |
| `state` | VARCHAR |  |
| `zip` | VARCHAR |  |
| `primary_provider_id` | VARCHAR |  |

### raw.ehr_procedures — 6,108,383 rows (6.1M)

| column | type | notes |
|---|---|---|
| `procedure_id` | BIGINT |  |
| `patient_id` | VARCHAR |  |
| `encounter_id` | VARCHAR |  |
| `cpt_code` | VARCHAR |  |
| `procedure_name` | VARCHAR |  |
| `performed_dt` | TIMESTAMP WITH TIME ZONE | range 2023-05-31 → 2026-05-31 |
| `performing_provider_id` | VARCHAR |  |

### raw.external_census_tract_demographics — 24,000 rows (24K)

| column | type | notes |
|---|---|---|
| `census_tract_geoid` | VARCHAR |  |
| `state` | VARCHAR |  |
| `county_name` | VARCHAR |  |
| `population` | BIGINT |  |
| `median_household_income` | DECIMAL(8,2) |  |
| `pct_age_under_18` | DECIMAL(4,2) |  |
| `pct_age_65_plus` | DECIMAL(4,2) |  |
| `pct_uninsured` | DECIMAL(4,2) |  |
| `pct_below_poverty` | DECIMAL(4,2) |  |
| `pct_hispanic` | DECIMAL(4,2) |  |
| `pct_black` | DECIMAL(4,2) |  |
| `pct_asian` | DECIMAL(4,2) |  |
| `pct_white_non_hispanic` | DECIMAL(4,2) |  |
| `polygon_wkt` | VARCHAR |  |

### raw.external_competitor_facilities — 2,800 rows (3K)

| column | type | notes |
|---|---|---|
| `external_facility_id` | VARCHAR |  |
| `facility_name` | VARCHAR |  |
| `facility_type` | VARCHAR |  |
| `system_owner` | VARCHAR |  |
| `address_line1` | VARCHAR |  |
| `city` | VARCHAR |  |
| `state` | VARCHAR |  |
| `zip` | VARCHAR |  |
| `latitude` | DECIMAL(8,6) |  |
| `longitude` | DECIMAL(9,6) |  |
| `specialties_offered` | VARCHAR |  |
| `total_beds` | BIGINT |  |

### raw.external_drive_time_isochrones — 252 rows (252)

| column | type | notes |
|---|---|---|
| `facility_id` | VARCHAR |  |
| `isochrone_minutes` | BIGINT |  |
| `polygon_wkt` | VARCHAR |  |
| `computed_at` | TIMESTAMP WITH TIME ZONE | range 2026-04-30 → 2026-04-30 |

### raw.ops_appointments — 3,247,474 rows (3.2M)

| column | type | notes |
|---|---|---|
| `appointment_id` | VARCHAR |  |
| `member_id` | VARCHAR |  |
| `provider_id` | VARCHAR |  |
| `facility_id` | VARCHAR |  |
| `scheduled_dt_local` | TIMESTAMP | range 2025-06-01 → 2026-05-31 |
| `duration_minutes` | BIGINT |  |
| `appointment_type` | VARCHAR |  |
| `specialty` | VARCHAR |  |
| `status` | VARCHAR |  |
| `booked_at` | TIMESTAMP WITH TIME ZONE | range 2025-04-01 → 2026-05-30 |

### raw.ops_bed_census_daily — 17,568 rows (18K)

| column | type | notes |
|---|---|---|
| `census_date` | DATE | range 2025-06-01 → 2026-06-01 |
| `facility_id` | VARCHAR |  |
| `unit` | VARCHAR |  |
| `total_beds` | BIGINT |  |
| `occupied_beds_midnight` | BIGINT |  |
| `peak_occupied_beds` | BIGINT |  |
| `avg_los_days` | DECIMAL(2,1) |  |

### raw.ops_facilities — 284 rows (284)

| column | type | notes |
|---|---|---|
| `facility_id` | VARCHAR |  |
| `facility_name` | VARCHAR |  |
| `facility_type` | VARCHAR |  |
| `ownership` | VARCHAR |  |
| `address_line1` | VARCHAR |  |
| `city` | VARCHAR |  |
| `state` | VARCHAR |  |
| `zip` | VARCHAR |  |
| `latitude` | DECIMAL(8,6) |  |
| `longitude` | DECIMAL(9,6) |  |
| `service_lines` | VARCHAR |  |
| `total_beds` | BIGINT |  |
| `total_ors` | BIGINT |  |
| `cost_index` | DECIMAL(4,3) |  |

### raw.ops_or_schedule — 82,531 rows (83K)

| column | type | notes |
|---|---|---|
| `or_case_id` | VARCHAR |  |
| `facility_id` | VARCHAR |  |
| `or_room` | VARCHAR |  |
| `scheduled_start_dt_local` | TIMESTAMP | range 2025-06-01 → 2026-05-30 |
| `scheduled_end_dt_local` | TIMESTAMP | range 2025-06-01 → 2026-05-30 |
| `actual_start_dt_local` | TIMESTAMP | range 2025-06-01 → 2026-05-30; 13% null |
| `actual_end_dt_local` | TIMESTAMP | range 2025-06-01 → 2026-05-30; 13% null |
| `cpt_code` | VARCHAR |  |
| `surgeon_id` | VARCHAR |  |
| `anesthesiologist_id` | VARCHAR |  |
| `case_class` | VARCHAR |  |
| `status` | VARCHAR |  |

### raw.ops_providers — 14,000 rows (14K)

| column | type | notes |
|---|---|---|
| `provider_id` | VARCHAR |  |
| `npi` | VARCHAR |  |
| `first_name` | VARCHAR |  |
| `last_name` | VARCHAR |  |
| `specialty` | VARCHAR |  |
| `employed_by_reina` | BOOLEAN |  |
| `primary_facility_id` | VARCHAR |  |
| `accepting_new_patients` | BOOLEAN |  |

### raw.ops_referrals — 1,200,000 rows (1.2M)

| column | type | notes |
|---|---|---|
| `referral_id` | VARCHAR |  |
| `member_id` | VARCHAR |  |
| `referring_provider_id` | VARCHAR |  |
| `referred_to_provider_id` | VARCHAR |  |
| `referred_to_facility_id` | VARCHAR |  |
| `specialty` | VARCHAR |  |
| `status` | VARCHAR |  |
| `issued_dt` | TIMESTAMP WITH TIME ZONE | range 2025-05-31 → 2026-05-31 |
| `scheduled_dt` | TIMESTAMP WITH TIME ZONE | range 2025-06-02 → 2026-07-15; 50% null |
| `completed_dt` | TIMESTAMP WITH TIME ZONE | range 2025-06-03 → 2026-07-28; 75% null |
| `urgency` | VARCHAR |  |

### raw.outreach_program_enrollments — 88,000 rows (88K)

| column | type | notes |
|---|---|---|
| `enrollment_id` | VARCHAR |  |
| `member_id` | VARCHAR |  |
| `program_id` | VARCHAR |  |
| `enrollment_dt` | TIMESTAMP WITH TIME ZONE | range 2019-12-31 → 2026-05-31 |
| `status` | VARCHAR |  |
| `completion_dt` | TIMESTAMP WITH TIME ZONE | range 2020-03-04 → 2027-05-21; 75% null |
| `source` | VARCHAR |  |

### raw.outreach_wellness_programs — 6 rows (6)

| column | type | notes |
|---|---|---|
| `program_id` | VARCHAR |  |
| `program_name` | VARCHAR |  |
| `description` | VARCHAR |  |
| `eligibility_rules` | VARCHAR |  |
| `modality` | VARCHAR |  |
| `expected_cost_offset_per_completion` | DECIMAL(6,2) |  |

### raw.payer_claims — 17,123,027 rows (17.1M)

| column | type | notes |
|---|---|---|
| `claim_id` | VARCHAR |  |
| `member_id` | VARCHAR |  |
| `provider_id` | VARCHAR |  |
| `facility_id` | VARCHAR |  |
| `service_date` | DATE | range 2023-06-01 → 2026-05-31 |
| `place_of_service_code` | VARCHAR |  |
| `procedure_code` | VARCHAR |  |
| `procedure_description` | VARCHAR |  |
| `primary_dx_code` | VARCHAR |  |
| `secondary_dx_codes` | VARCHAR |  |
| `service_line` | VARCHAR |  |
| `billed_amount` | DECIMAL(7,2) |  |
| `allowed_amount` | DECIMAL(7,2) |  |
| `plan_paid` | DECIMAL(7,2) |  |
| `member_paid` | DECIMAL(7,2) |  |
| `claim_status` | VARCHAR |  |
| `network_status` | VARCHAR |  |
| `submitted_date` | DATE | range 2023-06-01 → 2026-06-14 |
| `processed_date` | DATE | range 2023-07-01 → 2026-05-31; 1% null |

### raw.payer_employers — 820 rows (820)

| column | type | notes |
|---|---|---|
| `employer_id` | VARCHAR |  |
| `employer_name` | VARCHAR |  |
| `employee_count_band` | VARCHAR |  |
| `primary_state` | VARCHAR |  |
| `industry_sic` | VARCHAR |  |

### raw.payer_member_eligibility_history — 1,519,879 rows (1.5M)

| column | type | notes |
|---|---|---|
| `eligibility_id` | BIGINT |  |
| `member_id` | VARCHAR |  |
| `plan_id` | VARCHAR |  |
| `effective_date` | DATE | range 2020-01-01 → 2026-12-28 |
| `end_date` | DATE | range 2020-02-07 → 2030-03-26; 96% null |
| `coverage_type` | VARCHAR |  |

### raw.payer_members — 1,100,000 rows (1.1M)

| column | type | notes |
|---|---|---|
| `member_id` | VARCHAR |  |
| `first_name` | VARCHAR |  |
| `last_name` | VARCHAR |  |
| `dob` | DATE | range 1936-01-01 → 2026-12-28 |
| `gender` | VARCHAR |  |
| `address_line1` | VARCHAR |  |
| `address_line2` | VARCHAR |  |
| `city` | VARCHAR |  |
| `state` | VARCHAR |  |
| `zip` | VARCHAR |  |
| `latitude` | DECIMAL(8,6) |  |
| `longitude` | DECIMAL(9,6) |  |
| `primary_phone` | VARCHAR |  |
| `secondary_phone` | VARCHAR |  |
| `email` | VARCHAR |  |
| `preferred_language` | VARCHAR |  |
| `sms_consent` | BOOLEAN |  |
| `tcpa_window_start_local` | TIME |  |
| `tcpa_window_end_local` | TIME |  |
| `primary_pcp_provider_id` | VARCHAR |  |
| `plan_id` | VARCHAR |  |
| `employer_id` | VARCHAR |  |
| `enrollment_channel` | VARCHAR |  |
| `enrollment_date` | DATE | range 2020-01-01 → 2026-12-28 |
| `termination_date` | DATE | range 2020-02-07 → 2030-03-26; 95% null |
| `created_at` | TIMESTAMP WITH TIME ZONE | range 2019-12-31 → 2026-12-27 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | range 2020-01-03 → 2031-12-26 |

### raw.payer_plans — 42 rows (42)

| column | type | notes |
|---|---|---|
| `plan_id` | VARCHAR |  |
| `plan_name` | VARCHAR |  |
| `tier` | VARCHAR |  |
| `network_type` | VARCHAR |  |
| `deductible_individual` | DECIMAL(6,2) |  |
| `deductible_family` | DECIMAL(7,2) |  |
| `oop_max_individual` | DECIMAL(6,2) |  |
| `oop_max_family` | DECIMAL(7,2) |  |
| `market` | VARCHAR |  |
| `effective_year` | BIGINT |  |

### raw.pharmacy_rx_claims — 11,028,042 rows (11.0M)

| column | type | notes |
|---|---|---|
| `rx_claim_id` | VARCHAR |  |
| `member_id` | VARCHAR |  |
| `ndc_code` | VARCHAR |  |
| `drug_name` | VARCHAR |  |
| `days_supply` | BIGINT |  |
| `quantity` | DECIMAL(5,2) |  |
| `fill_date` | DATE | range 2023-06-01 → 2026-05-31 |
| `prescriber_npi` | VARCHAR |  |
| `pharmacy_id` | VARCHAR |  |
| `total_cost` | DECIMAL(6,2) |  |
| `plan_paid` | DECIMAL(6,2) |  |
| `member_paid` | DECIMAL(6,2) |  |

### marts._build_metadata — 7 rows (7)

| column | type | notes |
|---|---|---|
| `built_at` | TIMESTAMP WITH TIME ZONE | range 2026-09-01 → 2026-09-01 |
| `source_table` | VARCHAR |  |
| `row_count` | BIGINT |  |
| `event_column` | VARCHAR |  |
| `max_event_date` | DATE | range 2026-05-30 → 2026-05-31; 14% null |
| `incremental_column` | VARCHAR |  |
| `days_behind_today` | BIGINT |  |

### marts.facility_metrics — 284 rows (284)

| column | type | notes |
|---|---|---|
| `facility_id` | VARCHAR |  |
| `facility_name` | VARCHAR |  |
| `facility_type` | VARCHAR |  |
| `ownership` | VARCHAR |  |
| `city` | VARCHAR |  |
| `state` | VARCHAR |  |
| `zip` | VARCHAR |  |
| `latitude` | DECIMAL(8,6) |  |
| `longitude` | DECIMAL(9,6) |  |
| `service_lines` | VARCHAR |  |
| `total_beds` | BIGINT |  |
| `total_ors` | BIGINT |  |
| `cost_index` | DECIMAL(4,3) |  |
| `providers_based` | BIGINT |  |
| `providers_accepting` | BIGINT |  |
| `panel_total` | BIGINT |  |
| `panel_active` | BIGINT |  |
| `appts_scheduled` | BIGINT |  |
| `appts_completed` | BIGINT |  |
| `appts_no_show` | BIGINT |  |
| `appts_cancelled` | BIGINT |  |
| `pct_no_show` | DOUBLE |  |
| `pct_completed` | DOUBLE |  |
| `encounters` | BIGINT |  |
| `encounters_inpatient` | BIGINT |  |
| `encounters_ed` | BIGINT |  |
| `or_cases` | BIGINT |  |
| `or_cancelled` | BIGINT |  |
| `or_rooms_used` | BIGINT |  |
| `or_operating_days` | BIGINT |  |
| `or_booked_minutes` | HUGEINT |  |
| `or_utilization_pct` | DOUBLE |  |
| `bed_occupancy_pct` | DOUBLE |  |
| `avg_los_days` | DOUBLE |  |
| `claims` | BIGINT |  |
| `allowed_amount` | DECIMAL(38,2) |  |
| `plan_paid` | DECIMAL(38,2) |  |
| `appts_per_provider_based` | DOUBLE |  |
| `appts_per_panel_member` | DOUBLE |  |

### marts.identity_xwalk — 591,712 rows (592K)

| column | type | notes |
|---|---|---|
| `patient_id` | VARCHAR |  |
| `member_id` | VARCHAR |  |
| `match_method` | VARCHAR |  |
| `match_confidence` | DOUBLE |  |

### marts.market_flows — 12,443 rows (12K)

| column | type | notes |
|---|---|---|
| `member_city` | VARCHAR |  |
| `member_state` | VARCHAR |  |
| `care_city` | VARCHAR |  |
| `service_line` | VARCHAR |  |
| `is_acute` | BOOLEAN |  |
| `network_status` | VARCHAR |  |
| `ownership` | VARCHAR |  |
| `in_market` | BOOLEAN |  |
| `claims` | BIGINT |  |
| `allowed_musd` | DOUBLE |  |
| `plan_paid_musd` | DOUBLE |  |
| `if_owned_plan_paid_musd` | DOUBLE |  |

### marts.market_summary — 42 rows (42)

| column | type | notes |
|---|---|---|
| `city` | VARCHAR |  |
| `state` | VARCHAR |  |
| `members_total` | BIGINT |  |
| `members_active` | BIGINT |  |
| `owned_clinics` | BIGINT |  |
| `owned_hospitals` | BIGINT |  |
| `owned_urgent_care` | BIGINT |  |
| `owned_facilities` | BIGINT |  |
| `partner_facilities` | BIGINT |  |
| `owned_beds` | HUGEINT |  |
| `owned_ors` | HUGEINT |  |
| `providers_based_owned` | HUGEINT |  |
| `appts_completed_at_facilities_here` | HUGEINT |  |
| `claims` | BIGINT |  |
| `allowed_musd` | DOUBLE |  |
| `plan_paid_musd` | DOUBLE |  |
| `pct_allowed_owned` | DOUBLE |  |
| `pct_allowed_in_market` | DOUBLE |  |
| `acute_claims` | BIGINT |  |
| `acute_allowed_musd` | DOUBLE |  |
| `pct_acute_in_market` | DOUBLE |  |
| `median_miles_to_acute` | DOUBLE |  |
| `pct_acute_over_30mi` | DOUBLE |  |
| `nonowned_acute_plan_paid_musd` | DOUBLE |  |
| `acute_if_owned_plan_paid_musd` | DOUBLE |  |
| `recapture_plan_paid_musd` | DOUBLE |  |

## Canonical join paths

Every path below is asserted by `tests/test_warehouse.py` to execute with
zero orphan keys. Source of truth: `semantic/joins.json`.

| from | to | orphans | notes |
|---|---|---|---|
| `raw.payer_claims.member_id` | `raw.payer_members.member_id` | 0 | claims -> member demographics/geography |
| `raw.payer_claims.facility_id` | `raw.ops_facilities.facility_id` | 0 | claims -> facility, for owned/partner and city |
| `raw.payer_claims.provider_id` | `raw.ops_providers.provider_id` | 0 |  |
| `raw.ehr_encounters.patient_id` | `raw.ehr_patients.patient_id` | 0 |  |
| `raw.ehr_encounters.facility_id` | `raw.ops_facilities.facility_id` | 0 |  |
| `raw.ehr_procedures.patient_id` | `raw.ehr_patients.patient_id` | 0 |  |
| `raw.ehr_conditions.patient_id` | `raw.ehr_patients.patient_id` | 0 |  |
| `raw.ops_appointments.member_id` | `raw.payer_members.member_id` | 0 | appointments key on member_id, NOT patient_id — no crosswalk needed |
| `raw.ops_appointments.facility_id` | `raw.ops_facilities.facility_id` | 0 |  |
| `raw.ops_appointments.provider_id` | `raw.ops_providers.provider_id` | 0 | see caveat C1: this assignment is not a real staffing signal |
| `raw.ops_referrals.member_id` | `raw.payer_members.member_id` | 0 |  |
| `raw.ops_referrals.referred_to_facility_id` | `raw.ops_facilities.facility_id` | 0 | 22% null; NULL = referral not directed to a Reina Firme in-network facility |
| `raw.ops_or_schedule.facility_id` | `raw.ops_facilities.facility_id` | 0 |  |
| `raw.ops_bed_census_daily.facility_id` | `raw.ops_facilities.facility_id` | 0 |  |
| `raw.ops_providers.primary_facility_id` | `raw.ops_facilities.facility_id` | 0 | the ONLY trustworthy provider->facility assignment |
| `raw.pharmacy_rx_claims.member_id` | `raw.payer_members.member_id` | 0 |  |
| `raw.payer_member_eligibility_history.member_id` | `raw.payer_members.member_id` | 0 |  |
| `raw.payer_members.plan_id` | `raw.payer_plans.plan_id` | 0 |  |
| `raw.payer_members.employer_id` | `raw.payer_employers.employer_id` | 0 | 35% null; NULL = ACA/individual member, not employer group |
| `raw.outreach_program_enrollments.member_id` | `raw.payer_members.member_id` | 0 |  |
| `raw.outreach_program_enrollments.program_id` | `raw.outreach_wellness_programs.program_id` | 0 |  |
| `raw.external_drive_time_isochrones.facility_id` | `raw.ops_facilities.facility_id` | 0 |  |
| `marts.identity_xwalk.patient_id` | `raw.ehr_patients.patient_id` | 0 |  |
| `marts.identity_xwalk.member_id` | `raw.payer_members.member_id` | 0 |  |

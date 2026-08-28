# Data notes — Reina Firme Redshift

24 tables. Schemas: ehr, external, ops, outreach, payer, pharmacy


## ehr.conditions

| column | type | notes |
|---|---|---|
| condition_id | bigint | |
| patient_id | character varying | |
| icd10_code | character varying | |
| condition_name | character varying | |
| onset_date | date | |
| resolved_date | date | |
| status | character varying | |

Date range (onset_date): 2019-06-02 → 2023-06-01

## ehr.encounters

| column | type | notes |
|---|---|---|
| encounter_id | character varying | |
| patient_id | character varying | |
| facility_id | character varying | |
| provider_id | character varying | |
| encounter_class | character varying | |
| admission_dt | timestamp without time zone | |
| discharge_dt | timestamp without time zone | |
| length_of_stay_days | numeric | |
| primary_dx_code | character varying | |
| chief_complaint | character varying | |

Date range (admission_dt): 2023-06-01 00:00:21 → 2026-05-31 23:59:52

## ehr.medications

| column | type | notes |
|---|---|---|
| medication_id | bigint | |
| patient_id | character varying | |
| rxnorm_code | character varying | |
| medication_name | character varying | |
| dose | character varying | |
| start_date | date | |
| end_date | date | |
| prescriber_id | character varying | |

Date range (start_date): 2020-06-01 → 2023-06-01

## ehr.observations

| column | type | notes |
|---|---|---|
| observation_id | bigint | |
| patient_id | character varying | |
| encounter_id | character varying | |
| observation_loinc | character varying | |
| observation_name | character varying | |
| value_numeric | numeric | |
| value_text | character varying | |
| unit | character varying | |
| observation_dt | timestamp with time zone | |
| abnormal_flag | character varying | |

Date range (observation_dt): 2023-06-01 00:00:21+00:00 → 2026-06-01 00:29:45+00:00

## ehr.patients

| column | type | notes |
|---|---|---|
| patient_id | character varying | |
| mrn | character varying | |
| first_name | character varying | |
| last_name | character varying | |
| dob | date | |
| gender | character | |
| address_line1 | character varying | |
| city | character varying | |
| state | character | |
| zip | character varying | |
| primary_provider_id | character varying | |

Date range (dob): 1936-01-01 → 2026-12-28

## ehr.procedures

| column | type | notes |
|---|---|---|
| procedure_id | bigint | |
| patient_id | character varying | |
| encounter_id | character varying | |
| cpt_code | character varying | |
| procedure_name | character varying | |
| performed_dt | timestamp with time zone | |
| performing_provider_id | character varying | |

Date range (performed_dt): 2023-06-01 00:03:27+00:00 → 2026-06-01 00:55:38+00:00

## external.census_tract_demographics

| column | type | notes |
|---|---|---|
| census_tract_geoid | character varying | |
| state | character | |
| county_name | character varying | |
| population | integer | |
| median_household_income | numeric | |
| pct_age_under_18 | numeric | |
| pct_age_65_plus | numeric | |
| pct_uninsured | numeric | |
| pct_below_poverty | numeric | |
| pct_hispanic | numeric | |
| pct_black | numeric | |
| pct_asian | numeric | |
| pct_white_non_hispanic | numeric | |
| polygon_wkt | character varying | |

## external.competitor_facilities

| column | type | notes |
|---|---|---|
| external_facility_id | character varying | |
| facility_name | character varying | |
| facility_type | character varying | |
| system_owner | character varying | |
| address_line1 | character varying | |
| city | character varying | |
| state | character | |
| zip | character varying | |
| latitude | numeric | |
| longitude | numeric | |
| specialties_offered | character varying | |
| total_beds | integer | |

## external.drive_time_isochrones

| column | type | notes |
|---|---|---|
| facility_id | character varying | |
| isochrone_minutes | integer | |
| polygon_wkt | character varying | |
| computed_at | timestamp with time zone | |

Date range (computed_at): 2026-05-01 00:00:00+00:00 → 2026-05-01 00:00:00+00:00

## ops.appointments

| column | type | notes |
|---|---|---|
| appointment_id | character varying | |
| member_id | character varying | |
| provider_id | character varying | |
| facility_id | character varying | |
| scheduled_dt_local | timestamp without time zone | |
| duration_minutes | integer | |
| appointment_type | character varying | |
| specialty | character varying | |
| status | character varying | |
| booked_at | timestamp with time zone | |

Date range (scheduled_dt_local): 2025-06-01 00:00:05 → 2026-05-31 23:59:55

## ops.bed_census_daily

| column | type | notes |
|---|---|---|
| census_date | date | |
| facility_id | character varying | |
| unit | character varying | |
| total_beds | integer | |
| occupied_beds_midnight | integer | |
| peak_occupied_beds | integer | |
| avg_los_days | numeric | |

Date range (census_date): 2025-06-01 → 2026-06-01

## ops.facilities

| column | type | notes |
|---|---|---|
| facility_id | character varying | |
| facility_name | character varying | |
| facility_type | character varying | |
| ownership | character varying | |
| address_line1 | character varying | |
| city | character varying | |
| state | character | |
| zip | character varying | |
| latitude | numeric | |
| longitude | numeric | |
| service_lines | character varying | |
| total_beds | integer | |
| total_ors | integer | |
| cost_index | numeric | |

## ops.or_schedule

| column | type | notes |
|---|---|---|
| or_case_id | character varying | |
| facility_id | character varying | |
| or_room | character varying | |
| scheduled_start_dt_local | timestamp without time zone | |
| scheduled_end_dt_local | timestamp without time zone | |
| actual_start_dt_local | timestamp without time zone | |
| actual_end_dt_local | timestamp without time zone | |
| cpt_code | character varying | |
| surgeon_id | character varying | |
| anesthesiologist_id | character varying | |
| case_class | character varying | |
| status | character varying | |

Date range (scheduled_start_dt_local): 2025-06-01 01:26:00 → 2026-05-30 10:03:00

## ops.providers

| column | type | notes |
|---|---|---|
| provider_id | character varying | |
| npi | character varying | |
| first_name | character varying | |
| last_name | character varying | |
| specialty | character varying | |
| employed_by_reina | boolean | |
| primary_facility_id | character varying | |
| accepting_new_patients | boolean | |

## ops.referrals

| column | type | notes |
|---|---|---|
| referral_id | character varying | |
| member_id | character varying | |
| referring_provider_id | character varying | |
| referred_to_provider_id | character varying | |
| referred_to_facility_id | character varying | |
| specialty | character varying | |
| status | character varying | |
| issued_dt | timestamp with time zone | |
| scheduled_dt | timestamp with time zone | |
| completed_dt | timestamp with time zone | |
| urgency | character varying | |

Date range (issued_dt): 2025-06-01 00:00:00+00:00 → 2026-05-31 23:59:28+00:00

## outreach.communications_log

| column | type | notes |
|---|---|---|
| communication_id | character varying | |
| member_id | character varying | |
| channel | character varying | |
| direction | character varying | |
| template_id | character varying | |
| campaign_id | character varying | |
| sent_dt | timestamp with time zone | |
| response_class | character varying | |
| language_used | character varying | |

Date range (sent_dt): 2024-11-30 19:12:08+00:00 → 2026-05-31 23:59:46+00:00

## outreach.program_enrollments

| column | type | notes |
|---|---|---|
| enrollment_id | character varying | |
| member_id | character varying | |
| program_id | character varying | |
| enrollment_dt | timestamp with time zone | |
| status | character varying | |
| completion_dt | timestamp with time zone | |
| source | character varying | |

Date range (enrollment_dt): 2020-01-01 00:08:29+00:00 → 2026-05-31 21:58:32+00:00

## outreach.wellness_programs

| column | type | notes |
|---|---|---|
| program_id | character varying | |
| program_name | character varying | |
| description | character varying | |
| eligibility_rules | character varying | |
| modality | character varying | |
| expected_cost_offset_per_completion | numeric | |

## payer.claims

| column | type | notes |
|---|---|---|
| claim_id | character varying | |
| member_id | character varying | |
| provider_id | character varying | |
| facility_id | character varying | |
| service_date | date | |
| place_of_service_code | character varying | |
| procedure_code | character varying | |
| procedure_description | character varying | |
| primary_dx_code | character varying | |
| secondary_dx_codes | character varying | |
| service_line | character varying | |
| billed_amount | numeric | |
| allowed_amount | numeric | |
| plan_paid | numeric | |
| member_paid | numeric | |
| claim_status | character varying | |
| network_status | character varying | |
| submitted_date | date | |
| processed_date | date | |

Date range (service_date): 2023-06-01 → 2026-05-31

## payer.employers

| column | type | notes |
|---|---|---|
| employer_id | character varying | |
| employer_name | character varying | |
| employee_count_band | character varying | |
| primary_state | character | |
| industry_sic | character varying | |

## payer.member_eligibility_history

| column | type | notes |
|---|---|---|
| eligibility_id | bigint | |
| member_id | character varying | |
| plan_id | character varying | |
| effective_date | date | |
| end_date | date | |
| coverage_type | character varying | |

Date range (effective_date): 2020-01-01 → 2026-12-28

## payer.members

| column | type | notes |
|---|---|---|
| member_id | character varying | |
| first_name | character varying | |
| last_name | character varying | |
| dob | date | |
| gender | character | |
| address_line1 | character varying | |
| address_line2 | character varying | |
| city | character varying | |
| state | character | |
| zip | character varying | |
| latitude | numeric | |
| longitude | numeric | |
| primary_phone | character varying | |
| secondary_phone | character varying | |
| email | character varying | |
| preferred_language | character varying | |
| sms_consent | boolean | |
| tcpa_window_start_local | time without time zone | |
| tcpa_window_end_local | time without time zone | |
| primary_pcp_provider_id | character varying | |
| plan_id | character varying | |
| employer_id | character varying | |
| enrollment_channel | character varying | |
| enrollment_date | date | |
| termination_date | date | |
| created_at | timestamp with time zone | |
| updated_at | timestamp with time zone | |

Date range (dob): 1936-01-01 → 2026-12-28

## payer.plans

| column | type | notes |
|---|---|---|
| plan_id | character varying | |
| plan_name | character varying | |
| tier | character varying | |
| network_type | character varying | |
| deductible_individual | numeric | |
| deductible_family | numeric | |
| oop_max_individual | numeric | |
| oop_max_family | numeric | |
| market | character varying | |
| effective_year | integer | |

## pharmacy.rx_claims

| column | type | notes |
|---|---|---|
| rx_claim_id | character varying | |
| member_id | character varying | |
| ndc_code | character varying | |
| drug_name | character varying | |
| days_supply | integer | |
| quantity | numeric | |
| fill_date | date | |
| prescriber_npi | character varying | |
| pharmacy_id | character varying | |
| total_cost | numeric | |
| plan_paid | numeric | |
| member_paid | numeric | |

Date range (fill_date): 2023-06-01 → 2026-05-31

-- marts.facility_metrics — one row per facility (all 284, owned and partner).
--
-- Purpose: retire the dictionary caveats by encoding them in the data. Each
-- column below is a rule the agent previously had to remember and apply:
--   C1  providers_based comes from ops_providers.primary_facility_id, never
--       from ops_appointments.provider_id (which is randomly assigned).
--   C5  ownership and facility_type are columns, so "our network" is a filter,
--       not a thing you can forget.
--   R2  EVERYTHING here is windowed to the common 12-month ops window
--       (2025-06-01 .. 2026-05-31), so every column is comparable to every
--       other. Go to raw.payer_claims for the full 3-year claims history.
--   R6  allowed_amount and plan_paid are both carried; plan_paid is where the
--       owned-vs-partner cost difference actually lives.
--   OR  or_utilization_pct uses distinct or_room x actual operating days x 10h.
--       Using a 365-day year understates every facility by ~13pp.
--
-- Partner facilities legitimately have NULL/0 appointments, encounters, OR and
-- bed metrics: they are not in Reina Firme's own scheduling or clinical systems.
-- They still carry claims, which is how leakage is measured.

CREATE OR REPLACE TABLE marts.facility_metrics AS
WITH win AS (SELECT DATE '2025-06-01' AS lo, DATE '2026-06-01' AS hi),
providers AS (
    SELECT primary_facility_id AS facility_id,
           count(*)                                          AS providers_based,
           count(*) FILTER (WHERE accepting_new_patients)     AS providers_accepting
    FROM raw.ops_providers GROUP BY 1),
panel AS (
    SELECT p.primary_facility_id AS facility_id,
           count(m.member_id)                                 AS panel_total,
           count(m.member_id) FILTER (
               WHERE m.enrollment_date <= current_date
                 AND (m.termination_date IS NULL
                      OR m.termination_date > current_date))    AS panel_active
    FROM raw.ops_providers p
    LEFT JOIN raw.payer_members m ON m.primary_pcp_provider_id = p.provider_id
    GROUP BY 1),
appts AS (
    SELECT a.facility_id,
           count(*)                                                  AS appts_scheduled,
           count(*) FILTER (WHERE a.status = 'completed')             AS appts_completed,
           count(*) FILTER (WHERE a.status = 'no_show')               AS appts_no_show,
           count(*) FILTER (WHERE a.status LIKE 'cancelled%')         AS appts_cancelled
    FROM raw.ops_appointments a, win
    WHERE a.scheduled_dt_local >= win.lo AND a.scheduled_dt_local < win.hi
    GROUP BY 1),
enc AS (
    SELECT e.facility_id, count(*) AS encounters,
           count(*) FILTER (WHERE e.encounter_class = 'inpatient')  AS encounters_inpatient,
           count(*) FILTER (WHERE e.encounter_class = 'ed')         AS encounters_ed
    FROM raw.ehr_encounters e, win
    WHERE e.admission_dt >= win.lo AND e.admission_dt < win.hi
    GROUP BY 1),
ors AS (
    SELECT o.facility_id,
           count(*)                                                     AS or_cases,
           count(*) FILTER (WHERE o.actual_start_dt_local IS NULL)       AS or_cancelled,
           count(DISTINCT o.or_room)                                     AS or_rooms_used,
           count(DISTINCT o.scheduled_start_dt_local::date)              AS or_operating_days,
           sum(date_diff('minute', o.scheduled_start_dt_local, o.scheduled_end_dt_local))
               FILTER (WHERE o.actual_start_dt_local IS NOT NULL)        AS or_booked_minutes
    FROM raw.ops_or_schedule o, win
    WHERE o.scheduled_start_dt_local >= win.lo AND o.scheduled_start_dt_local < win.hi
    GROUP BY 1),
beds AS (
    SELECT c.facility_id,
           avg(c.occupied_beds_midnight * 100.0 / nullif(c.total_beds, 0)) AS bed_occupancy_pct,
           avg(c.avg_los_days)                                             AS avg_los_days
    FROM raw.ops_bed_census_daily c, win
    WHERE c.census_date >= win.lo AND c.census_date < win.hi
    GROUP BY 1),
clm AS (   -- claims where THIS facility delivered the care
    SELECT c.facility_id,
           count(*)                  AS claims,
           sum(c.allowed_amount)     AS allowed_amount,
           sum(c.plan_paid)          AS plan_paid
    FROM raw.payer_claims c, win
    WHERE c.service_date >= win.lo AND c.service_date < win.hi
    GROUP BY 1)
SELECT
    f.facility_id, f.facility_name, f.facility_type, f.ownership,
    f.city, f.state, f.zip, f.latitude, f.longitude,
    f.service_lines, f.total_beds, f.total_ors, f.cost_index,

    coalesce(pr.providers_based, 0)     AS providers_based,
    coalesce(pr.providers_accepting, 0) AS providers_accepting,
    coalesce(pn.panel_total, 0)         AS panel_total,
    coalesce(pn.panel_active, 0)        AS panel_active,

    coalesce(a.appts_scheduled, 0)      AS appts_scheduled,
    coalesce(a.appts_completed, 0)      AS appts_completed,
    coalesce(a.appts_no_show, 0)        AS appts_no_show,
    coalesce(a.appts_cancelled, 0)      AS appts_cancelled,
    round(a.appts_no_show   * 100.0 / nullif(a.appts_scheduled, 0), 1) AS pct_no_show,
    round(a.appts_completed * 100.0 / nullif(a.appts_scheduled, 0), 1) AS pct_completed,

    coalesce(e.encounters, 0)           AS encounters,
    coalesce(e.encounters_inpatient, 0) AS encounters_inpatient,
    coalesce(e.encounters_ed, 0)        AS encounters_ed,

    o.or_cases, o.or_cancelled, o.or_rooms_used, o.or_operating_days, o.or_booked_minutes,
    -- correct denominator: rooms x days actually operated x 10 staffed hours
    round(o.or_booked_minutes * 100.0
          / nullif(o.or_rooms_used * o.or_operating_days * 10 * 60, 0), 1) AS or_utilization_pct,
    round(b.bed_occupancy_pct, 1)       AS bed_occupancy_pct,
    round(b.avg_los_days, 2)            AS avg_los_days,

    coalesce(c.claims, 0)               AS claims,
    coalesce(c.allowed_amount, 0)       AS allowed_amount,
    coalesce(c.plan_paid, 0)            AS plan_paid,

    -- safe normalized utilization: the only denominators that mean anything
    round(a.appts_completed * 1.0 / nullif(pr.providers_based, 0), 1) AS appts_per_provider_based,
    round(a.appts_completed * 1.0 / nullif(pn.panel_active, 0), 3)    AS appts_per_panel_member
FROM raw.ops_facilities f
LEFT JOIN providers pr USING (facility_id)
LEFT JOIN panel     pn USING (facility_id)
LEFT JOIN appts      a USING (facility_id)
LEFT JOIN enc        e USING (facility_id)
LEFT JOIN ors        o USING (facility_id)
LEFT JOIN beds       b USING (facility_id)
LEFT JOIN clm        c USING (facility_id);

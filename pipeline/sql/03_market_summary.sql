-- marts.market_summary — one row per market (city), the Q1 answer as a table.
--
-- A "market" has two sides that must not be conflated: a MEMBER population
-- (payer_members.city) and a FACILITY footprint (ops_facilities.city). Both are
-- keyed on city here so a market can be judged on supply vs demand.
--
-- Encodes the rules that market comparisons kept getting wrong:
--   C6  Do NOT rank markets by pct_allowed_owned — it is 61-63% in every city
--       and carries no signal. It is included ONLY so that uniformity is
--       visible rather than rediscovered. Rank on the geographic columns:
--       pct_acute_in_market, median_miles_to_acute, owned_* composition.
--   R6  Savings live in plan_paid, not allowed_amount (allowed is flat across
--       network status). recapture_plan_paid_musd reprices non-owned acute
--       volume at the owned plan_paid ratio for that service line.
--   R2  All measures windowed to 2025-06-01 .. 2026-05-31.
--
-- "Acute" = service_line in (surgery, cardiology, er, oncology): the hospital
-- lines. Ambulatory lines (primary_care, imaging, labs, behavioral) are already
-- ~72% retained network-wide and are not the growth question.
-- Distances are straight-line (haversine) miles, member home -> serving
-- facility. Real drive time would use raw.external_drive_time_isochrones.

CREATE OR REPLACE TABLE marts.market_summary AS
WITH win AS (SELECT DATE '2025-06-01' AS lo, DATE '2026-06-01' AS hi),
acute AS (SELECT ['surgery', 'cardiology', 'er', 'oncology'] AS lines),
mem AS (
    SELECT member_id, city, state, latitude AS lat, longitude AS lon,
           (termination_date IS NULL OR termination_date > current_date) AS is_active
    FROM raw.payer_members),
members AS (
    SELECT city, any_value(state) AS state,
           count(*) AS members_total,
           count(*) FILTER (WHERE is_active) AS members_active
    FROM mem GROUP BY 1),
footprint AS (   -- facilities physically located in this city
    SELECT city,
           count(*) FILTER (WHERE ownership = 'owned' AND facility_type = 'clinic')      AS owned_clinics,
           count(*) FILTER (WHERE ownership = 'owned' AND facility_type = 'hospital')    AS owned_hospitals,
           count(*) FILTER (WHERE ownership = 'owned' AND facility_type = 'urgent_care') AS owned_urgent_care,
           count(*) FILTER (WHERE ownership = 'owned')                                   AS owned_facilities,
           count(*) FILTER (WHERE ownership = 'partner')                                 AS partner_facilities,
           sum(providers_based) FILTER (WHERE ownership = 'owned')                        AS providers_based_owned,
           sum(appts_completed)                                                          AS appts_completed,
           sum(total_beds) FILTER (WHERE ownership = 'owned')                             AS owned_beds,
           sum(total_ors)  FILTER (WHERE ownership = 'owned')                             AS owned_ors
    FROM marts.facility_metrics GROUP BY 1),
owned_ratio AS (   -- what share of allowed does the plan pay when care is owned?
    SELECT service_line, avg(plan_paid / nullif(allowed_amount, 0)) AS ratio
    FROM raw.payer_claims, win
    WHERE network_status = 'owned' AND service_date >= win.lo AND service_date < win.hi
    GROUP BY 1),
cl AS (   -- every claim attributed to the MEMBER's market, wherever delivered
    SELECT m.city,
           c.service_line, c.allowed_amount, c.plan_paid,
           f.ownership, f.city AS care_city,
           (f.city = m.city) AS in_market,
           list_contains((SELECT lines FROM acute), c.service_line) AS is_acute,
           3959 * 2 * asin(sqrt(
               pow(sin(radians(f.latitude - m.lat) / 2), 2)
             + cos(radians(m.lat)) * cos(radians(f.latitude))
               * pow(sin(radians(f.longitude - m.lon) / 2), 2))) AS miles
    FROM raw.payer_claims c
    JOIN mem m USING (member_id)
    JOIN raw.ops_facilities f ON f.facility_id = c.facility_id
    CROSS JOIN win
    WHERE c.service_date >= win.lo AND c.service_date < win.hi),
claims AS (
    SELECT city,
           count(*)                          AS claims,
           sum(allowed_amount) / 1e6         AS allowed_musd,
           sum(plan_paid) / 1e6              AS plan_paid_musd,
           100.0 * sum(CASE WHEN ownership = 'owned' THEN allowed_amount ELSE 0 END)
                 / sum(allowed_amount)       AS pct_allowed_owned,
           100.0 * sum(CASE WHEN in_market   THEN allowed_amount ELSE 0 END)
                 / sum(allowed_amount)       AS pct_allowed_in_market
    FROM cl GROUP BY 1),
acute_agg AS (
    SELECT city,
           count(*)                                        AS acute_claims,
           sum(allowed_amount) / 1e6                       AS acute_allowed_musd,
           100.0 * count(*) FILTER (WHERE in_market) / count(*) AS pct_acute_in_market,
           median(miles)                                   AS median_miles_to_acute,
           100.0 * count(*) FILTER (WHERE miles > 30) / count(*) AS pct_acute_over_30mi,
           sum(plan_paid) FILTER (WHERE ownership <> 'owned') / 1e6 AS nonowned_acute_plan_paid_musd
    FROM cl WHERE is_acute GROUP BY 1),
recapture AS (   -- reprice non-owned acute volume at the owned plan_paid ratio
    SELECT cl.city,
           sum(cl.allowed_amount * r.ratio) / 1e6 AS acute_if_owned_plan_paid_musd
    FROM cl JOIN owned_ratio r USING (service_line)
    WHERE cl.is_acute AND cl.ownership <> 'owned'
    GROUP BY 1)
SELECT
    m.city, m.state, m.members_total, m.members_active,
    coalesce(fp.owned_clinics, 0)      AS owned_clinics,
    coalesce(fp.owned_hospitals, 0)    AS owned_hospitals,
    coalesce(fp.owned_urgent_care, 0)  AS owned_urgent_care,
    coalesce(fp.owned_facilities, 0)   AS owned_facilities,
    coalesce(fp.partner_facilities, 0) AS partner_facilities,
    fp.owned_beds, fp.owned_ors,
    coalesce(fp.providers_based_owned, 0) AS providers_based_owned,
    coalesce(fp.appts_completed, 0)       AS appts_completed_at_facilities_here,

    c.claims, round(c.allowed_musd, 1) AS allowed_musd,
    round(c.plan_paid_musd, 1)         AS plan_paid_musd,
    round(c.pct_allowed_owned, 1)      AS pct_allowed_owned,       -- see C6: uniform, no signal
    round(c.pct_allowed_in_market, 1)  AS pct_allowed_in_market,

    a.acute_claims, round(a.acute_allowed_musd, 1) AS acute_allowed_musd,
    round(a.pct_acute_in_market, 1)    AS pct_acute_in_market,
    round(a.median_miles_to_acute, 1)  AS median_miles_to_acute,
    round(a.pct_acute_over_30mi, 1)    AS pct_acute_over_30mi,

    round(a.nonowned_acute_plan_paid_musd, 1) AS nonowned_acute_plan_paid_musd,
    round(rc.acute_if_owned_plan_paid_musd, 1) AS acute_if_owned_plan_paid_musd,
    round(a.nonowned_acute_plan_paid_musd - rc.acute_if_owned_plan_paid_musd, 1)
        AS recapture_plan_paid_musd
FROM members m
LEFT JOIN footprint fp USING (city)
LEFT JOIN claims    c  USING (city)
LEFT JOIN acute_agg a  USING (city)
LEFT JOIN recapture rc USING (city);

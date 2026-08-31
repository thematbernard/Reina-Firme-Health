-- Q1: where should we open the next facility, and what services should it offer?
-- Every number in analysis/01_next_facility.md, in section order.
-- Run: make analysis   (or: uv run python analysis/run.py analysis/01_next_facility.sql)
--
-- Definitions used throughout, stated once:
--   acute care     = service_line in (surgery, cardiology, er, oncology)
--   corridor       = member city in (Sacramento, Stockton, Modesto)
--   trailing 12mo  = service_date >= 2025-06-01 (claims run 2023-06-01 -> 2026-05-31)
--   "in corridor"  = the facility that served the claim is in a corridor city,
--                    regardless of ownership -- this is an ACCESS measure, not a
--                    market-share measure. Ownership share is caveat C6 and
--                    carries no cross-market signal (block 3).

-- §1 — Sacramento is the access outlier.
-- The whole slide-2 table is one SELECT from one mart, no joins.
SELECT city,
       members_total,
       members_active,
       owned_hospitals,
       owned_urgent_care,
       owned_clinics,
       pct_acute_in_market,
       median_miles_to_acute,
       pct_acute_over_30mi,
       round(100 - pct_allowed_in_market, 1) AS pct_dollars_out_of_market,
       allowed_musd,
       recapture_plan_paid_musd
FROM marts.market_summary
WHERE city IN ('Sacramento', 'Atlanta', 'Oakland', 'Stockton', 'Modesto')
ORDER BY members_active DESC;

-- §1 — the out-of-market dollar figure, and why we quote the percentage.
-- Same percentage on any window; the dollars move because claims history has
-- partial years at both ends and a median 67-day adjudication lag.
WITH mm AS (
    SELECT member_id, city AS member_city
    FROM raw.payer_members
    WHERE city = 'Sacramento'
)
SELECT 'trailing 12 months'                                              AS basis,
       round(sum(c.allowed_amount) / 1e6, 1)                             AS allowed_musd,
       round(sum(CASE WHEN f.city <> mm.member_city THEN c.allowed_amount ELSE 0 END) / 1e6, 1)
                                                                         AS out_of_market_musd,
       round(100.0 * sum(CASE WHEN f.city <> mm.member_city THEN c.allowed_amount ELSE 0 END)
             / sum(c.allowed_amount), 1)                                 AS pct_out_of_market
FROM raw.payer_claims c
JOIN mm USING (member_id)
JOIN raw.ops_facilities f ON f.facility_id = c.facility_id
WHERE c.service_date >= DATE '2025-06-01'
UNION ALL
SELECT '3-year total / 3',
       round(sum(c.allowed_amount) / 3e6, 1),
       round(sum(CASE WHEN f.city <> mm.member_city THEN c.allowed_amount ELSE 0 END) / 3e6, 1),
       round(100.0 * sum(CASE WHEN f.city <> mm.member_city THEN c.allowed_amount ELSE 0 END)
             / sum(c.allowed_amount), 1)
FROM raw.payer_claims c
JOIN mm USING (member_id)
JOIN raw.ops_facilities f ON f.facility_id = c.facility_id;

-- §2 — why market ranking cannot use ownership share (caveat C6).
-- Owned dollar share is 61-63% in every large market: no signal.
WITH mm AS (SELECT member_id, city FROM raw.payer_members)
SELECT mm.city,
       round(100.0 * sum(CASE WHEN f.ownership = 'owned' THEN c.allowed_amount ELSE 0 END)
             / sum(c.allowed_amount), 1) AS pct_allowed_owned
FROM raw.payer_claims c
JOIN mm USING (member_id)
JOIN raw.ops_facilities f ON f.facility_id = c.facility_id
GROUP BY mm.city
HAVING count(*) > 200000
ORDER BY pct_allowed_owned;

-- §3 — the three-city corridor.
SELECT sum(members_active)                     AS corridor_active_members,
       round(sum(recapture_plan_paid_musd), 1) AS corridor_recapture_plan_paid_musd
FROM marts.market_summary
WHERE city IN ('Sacramento', 'Stockton', 'Modesto');

-- §3 — the corridor is a region, not a catchment.
-- Straight-line miles from the Sacramento owned-clinic centroid to active
-- member homes. Modesto's median is 71.9 -- the same trip §1 calls
-- unacceptable -- so a Sacramento hospital does not serve it.
WITH sac AS (
    SELECT avg(latitude) AS lat, avg(longitude) AS lon
    FROM raw.ops_facilities WHERE ownership = 'owned' AND city = 'Sacramento'
),
mem AS (
    SELECT city, latitude AS lat, longitude AS lon
    FROM raw.payer_members
    WHERE city IN ('Sacramento', 'Stockton', 'Modesto')
      AND enrollment_date <= current_date
      AND (termination_date IS NULL OR termination_date > current_date)
),
d AS (
    SELECT m.city,
           3959 * 2 * asin(sqrt(pow(sin(radians(s.lat - m.lat) / 2), 2)
             + cos(radians(m.lat)) * cos(radians(s.lat))
               * pow(sin(radians(s.lon - m.lon) / 2), 2))) AS mi
    FROM mem m CROSS JOIN sac s
)
SELECT city,
       count(*)                                                        AS active_members,
       round(median(mi), 1)                                            AS median_miles_to_site,
       round(100.0 * count(*) FILTER (WHERE mi <= 30) / count(*), 1)   AS pct_within_30mi,
       round(100.0 * count(*) FILTER (WHERE mi <= 45) / count(*), 1)   AS pct_within_45mi
FROM d GROUP BY 1 ORDER BY 2 DESC;

-- §5 — sizing anchors: capacity per active member, network and Atlanta-only.
-- Observed utilization cannot validate a capacity plan here (all 8 owned
-- hospitals sit at 54.1-55.4% occupancy regardless of size), so per-member
-- ratios are the only defensible basis.
WITH net AS (
    SELECT sum(total_beds) AS beds, sum(total_ors) AS ors
    FROM marts.facility_metrics WHERE ownership = 'owned'
),
book AS (SELECT sum(members_active) AS m FROM marts.market_summary),
atl AS (
    SELECT total_beds AS beds, total_ors AS ors
    FROM marts.facility_metrics WHERE facility_id = 'FAC-00006'
),
catchment(label, members) AS (
    VALUES ('Sacramento only', 50615),
           ('Sacramento + reachable Stockton', 60515),
           ('all three markets', 102540)
)
SELECT c.label,
       c.members,
       round(net.beds * c.members / book.m)              AS beds_network_ratio,
       round(atl.beds * c.members / 122480.0)            AS beds_atlanta_ratio,
       round(net.ors  * c.members / book.m, 1)           AS ors_network_ratio
FROM catchment c CROSS JOIN net CROSS JOIN book CROSS JOIN atl;

-- §4 — what services: only the hospital lines leak.
-- One table, no joins. This is the query the recommendation turns on: ~12%
-- served locally for the hospital lines, ~72% for ambulatory. Note the
-- catchment is three cities -- marts.market_flows carries care_city precisely
-- so a multi-city catchment is a WHERE clause rather than a re-derivation.
SELECT service_line,
       round(sum(allowed_musd), 1)                                       AS allowed_musd,
       round(100.0 * sum(allowed_musd)
                     FILTER (WHERE care_city IN ('Sacramento', 'Stockton', 'Modesto'))
             / sum(allowed_musd), 1)                                     AS pct_served_in_corridor
FROM marts.market_flows
WHERE member_city IN ('Sacramento', 'Stockton', 'Modesto')
GROUP BY 1
ORDER BY 2 DESC;

-- §4 — the same question one level down: recapture by service line, so the
-- build list is ordered by recoverable plan_paid rather than by gross spend
-- (rule R6). This covers ALL lines, so it sums to more than the $33.2M acute
-- figure in §3 -- that one is acute lines only. Compare like with like.
SELECT service_line,
       round(sum(plan_paid_musd - if_owned_plan_paid_musd), 1) AS recapture_plan_paid_musd
FROM marts.market_flows
WHERE member_city IN ('Sacramento', 'Stockton', 'Modesto')
  AND ownership <> 'owned'
GROUP BY 1
ORDER BY 2 DESC;

-- §5 — sizing: benchmarked on Atlanta's owned hospital.
SELECT f.facility_id,
       f.city,
       f.total_beds,
       f.total_ors,
       f.or_utilization_pct,
       f.bed_occupancy_pct,
       m.members_active AS market_active_members
FROM marts.facility_metrics f
JOIN marts.market_summary m ON m.city = f.city
WHERE f.facility_id = 'FAC-00006';

-- §5 — "just redirect volume to existing capacity" fails: every owned hospital
-- has headroom, but the nearest one is 75 miles from a Sacramento member.
SELECT min(or_utilization_pct)  AS or_util_min,
       max(or_utilization_pct)  AS or_util_max,
       min(bed_occupancy_pct)   AS bed_occ_min,
       max(bed_occupancy_pct)   AS bed_occ_max
FROM marts.facility_metrics
WHERE ownership = 'owned' AND facility_type = 'hospital';

-- §5 — the saving is in plan_paid, not allowed_amount (rule R6).
-- avg allowed is flat wherever care happens; the paid share is not.
SELECT network_status,
       round(avg(allowed_amount), 0)                            AS avg_allowed,
       round(avg(plan_paid / nullif(allowed_amount, 0)), 3)      AS plan_paid_ratio
FROM raw.payer_claims
WHERE service_date >= DATE '2025-06-01'
GROUP BY 1
ORDER BY plan_paid_ratio;

-- §6 — the honest caveat, pinned so the narrative cannot drift:
-- ranking by recapture dollars alone picks Atlanta, not Sacramento.
SELECT city, recapture_plan_paid_musd
FROM marts.market_summary
ORDER BY recapture_plan_paid_musd DESC
LIMIT 5;

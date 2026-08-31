-- marts.market_flows — where each market's spend is delivered, by service line.
--
-- Grain: member_city x care_city x service_line x network_status (~12.4K rows).
-- One row = "members of X spent $N on line L, delivered in Y, at a facility of
-- network status Z, in the trailing 12 months."
--
-- Why this mart exists. marts.market_summary answers "which market has an
-- access gap" but collapses every hospital line into one acute_* group, so it
-- cannot answer the second half of Q1 — *what services should the facility
-- offer*. That answer previously required a three-table raw join
-- (payer_claims x payer_members x ops_facilities), which is exactly the
-- hand-assembly the marts exist to remove. It is also the only shape that
-- supports a MULTI-CITY catchment: retention for a Sacramento-Stockton-Modesto
-- corridor is not derivable from per-city percentages, because a Sacramento
-- member treated in Stockton is out-of-market at city grain and in-corridor at
-- corridor grain. Carrying care_city makes both readings one GROUP BY.
--
-- Rules encoded here:
--   R2  Windowed to 2025-06-01 .. 2026-05-31, the same 12 months as every other
--       mart column, so a comparison cannot silently mix windows.
--   R6  Savings live in plan_paid, not allowed_amount. allowed_musd,
--       plan_paid_musd and if_owned_plan_paid_musd are all carried, and all
--       three are additive, so recapture for any set of cities and any set of
--       lines is a SUM rather than a re-derivation.
--   C3  Members are attributed by their own city; claims follow the member, not
--       the facility. "Leakage" is therefore always member-relative.
--   C5  ownership is a column at grain — no need to remember to filter it.
--
-- Deliberately NOT carried: distance. A median is not additive, so a median
-- column at this grain would be silently wrong the moment anyone grouped it.
-- Distance lives in market_summary.median_miles_to_acute, at a grain where the
-- median is computed over the underlying claims.
--
-- ownership is functionally dependent on network_status (owned -> owned;
-- partner -> in_network_partner | out_of_network). Both are carried because
-- ownership is the word the facility tables use and network_status is the word
-- the claims use, and mixing them up is how the R6 mistake gets made.

CREATE OR REPLACE TABLE marts.market_flows AS
WITH win AS (SELECT DATE '2025-06-01' AS lo, DATE '2026-06-01' AS hi),
acute AS (SELECT ['surgery', 'cardiology', 'er', 'oncology'] AS lines),
mem AS (
    SELECT member_id, city, state
    FROM raw.payer_members),
owned_ratio AS (   -- what share of allowed does the plan pay when care is owned?
    SELECT service_line, avg(plan_paid / nullif(allowed_amount, 0)) AS ratio
    FROM raw.payer_claims, win
    WHERE network_status = 'owned' AND service_date >= win.lo AND service_date < win.hi
    GROUP BY 1),
cl AS (
    SELECT m.city  AS member_city,
           m.state AS member_state,
           f.city  AS care_city,
           c.service_line,
           c.network_status,
           f.ownership,
           c.allowed_amount,
           c.plan_paid
    FROM raw.payer_claims c
    JOIN mem m USING (member_id)
    JOIN raw.ops_facilities f ON f.facility_id = c.facility_id
    CROSS JOIN win
    WHERE c.service_date >= win.lo AND c.service_date < win.hi)
SELECT
    cl.member_city,
    any_value(cl.member_state)                    AS member_state,
    cl.care_city,
    cl.service_line,
    list_contains((SELECT lines FROM acute), cl.service_line) AS is_acute,
    cl.network_status,
    any_value(cl.ownership)                       AS ownership,
    (cl.member_city = cl.care_city)               AS in_market,
    count(*)                                      AS claims,
    round(sum(cl.allowed_amount) / 1e6, 4)        AS allowed_musd,
    round(sum(cl.plan_paid) / 1e6, 4)             AS plan_paid_musd,
    -- what the plan would have paid for this volume at the owned ratio for this
    -- line. Equals plan_paid_musd on owned rows by construction; the difference
    -- on non-owned rows is the recapture opportunity.
    round(sum(cl.allowed_amount * r.ratio) / 1e6, 4) AS if_owned_plan_paid_musd
FROM cl
JOIN owned_ratio r USING (service_line)
GROUP BY cl.member_city, cl.care_city, cl.service_line, cl.network_status,
         (cl.member_city = cl.care_city),
         list_contains((SELECT lines FROM acute), cl.service_line);

-- Decomposition of the claim: "utilization at our Sacramento clinic is 40%
-- below our Atlanta clinic of similar size."
--
-- Reproduce:  make analysis
-- Individual numbered blocks can also be pasted through the MCP run_query tool
-- (temp view first, then the block you want).
--
-- Conclusion: the gap does not exist. See analysis/02_sacramento_vs_atlanta.md.

-- Reusable per-clinic fact base -----------------------------------------------
CREATE OR REPLACE TEMP VIEW clinic_facts AS
WITH panel AS (   -- attributed panel: members whose PCP is BASED at the facility
    SELECT p.primary_facility_id AS facility_id, count(m.member_id) AS panel
    FROM raw.ops_providers p
    LEFT JOIN raw.payer_members m ON m.primary_pcp_provider_id = p.provider_id
    GROUP BY 1),
prov AS (         -- real staffing; see caveat C1 re ops_appointments.provider_id
    SELECT primary_facility_id AS facility_id, count(*) AS providers
    FROM raw.ops_providers GROUP BY 1),
vol AS (
    SELECT facility_id,
           count(*) FILTER (WHERE status = 'completed') AS completed,
           count(*) FILTER (WHERE status = 'no_show')   AS no_show,
           count(*)                                     AS scheduled
    FROM raw.ops_appointments GROUP BY 1),
enc AS (          -- second, independent volume source
    SELECT facility_id, count(*) AS encounters
    FROM raw.ehr_encounters
    WHERE admission_dt >= '2025-06-01' AND admission_dt < '2026-06-01'  -- match ops window (R2)
    GROUP BY 1)
SELECT f.city, f.facility_id, pn.panel, pr.providers,
       v.completed, v.scheduled, e.encounters,
       round(100.0 * v.no_show / v.scheduled, 1)      AS pct_no_show,
       round(v.completed * 1.0 / pr.providers, 1)      AS per_provider,
       round(v.completed * 1.0 / pn.panel, 3)          AS per_panel_member
FROM raw.ops_facilities f
JOIN vol  v  USING (facility_id)
JOIN enc  e  USING (facility_id)
JOIN panel pn USING (facility_id)
JOIN prov pr USING (facility_id)
WHERE f.ownership = 'owned' AND f.facility_type = 'clinic';   -- caveat C5

-- 1. Is a 40% gap even possible? Spread of raw throughput, all 64 clinics.
--    Result: CV 0.68%, max/min 1.029 -> widest possible gap is 2.9%.
SELECT count(*) AS n_clinics, min(completed), max(completed),
       round(stddev(completed), 0) AS sd,
       round(100.0 * stddev(completed) / avg(completed), 2) AS cv_pct,
       round(max(completed) * 1.0 / min(completed), 3)      AS max_min_ratio
FROM clinic_facts;

-- 2. Same test on an independent volume source. Result: max/min 1.068.
SELECT round(100.0 * stddev(encounters) / avg(encounters), 2) AS cv_pct,
       round(max(encounters) * 1.0 / min(encounters), 3)      AS max_min_ratio
FROM clinic_facts;

-- 3. The size-matched pair (panels within 0.1%): FAC-00015 vs FAC-00052.
--    Result: throughput differs by 0.4%, not 40%.
SELECT * FROM clinic_facts WHERE facility_id IN ('FAC-00015', 'FAC-00052') ORDER BY city;

-- 4. Denominator sensitivity: the "gap" is entirely an artifact of the
--    denominator, and every denominator favours Sacramento.
SELECT city, count(*) AS clinics,
       round(avg(completed), 0)          AS per_clinic,
       round(sum(completed) * 1.0 / sum(providers), 1) AS per_provider,
       round(sum(completed) * 1.0 / sum(panel), 3)     AS per_panel_member
FROM clinic_facts WHERE city IN ('Sacramento', 'Atlanta') GROUP BY 1;

-- 5. The real structural difference: Sacramento has no owned hospital or
--    urgent care, so its members export care out of market.
SELECT city,
       count(*) FILTER (WHERE facility_type = 'clinic')      AS clinics,
       count(*) FILTER (WHERE facility_type = 'hospital')    AS hospitals,
       count(*) FILTER (WHERE facility_type = 'urgent_care') AS urgent_care
FROM raw.ops_facilities
WHERE ownership = 'owned' AND city IN ('Sacramento', 'Atlanta') GROUP BY 1;

-- 6. Where each market's members actually receive care.
WITH mm AS (SELECT member_id, city AS member_city FROM raw.payer_members
            WHERE city IN ('Sacramento', 'Atlanta'))
SELECT mm.member_city, f.city AS care_city, f.ownership, count(*) AS claims
FROM raw.payer_claims c JOIN mm USING (member_id)
JOIN raw.ops_facilities f ON f.facility_id = c.facility_id
GROUP BY 1, 2, 3
QUALIFY row_number() OVER (PARTITION BY mm.member_city ORDER BY count(*) DESC) <= 6
ORDER BY mm.member_city, claims DESC;

-- 7. Out-of-market dollar leakage per market (the real finding).
WITH mm AS (SELECT member_id, city AS member_city FROM raw.payer_members
            WHERE city IN ('Sacramento', 'Atlanta'))
SELECT mm.member_city,
       round(sum(c.allowed_amount) / 1e6, 1) AS total_musd,
       round(sum(CASE WHEN f.city <> mm.member_city THEN c.allowed_amount ELSE 0 END) / 1e6, 1)
           AS out_of_market_musd,
       round(100.0 * sum(CASE WHEN f.city <> mm.member_city THEN c.allowed_amount ELSE 0 END)
             / sum(c.allowed_amount), 1) AS pct_out_of_market
FROM raw.payer_claims c JOIN mm USING (member_id)
JOIN raw.ops_facilities f ON f.facility_id = c.facility_id
GROUP BY 1;

-- 8. Mechanism: it is hospital care that leaves. Run per market.
WITH mm AS (SELECT member_id, city AS member_city FROM raw.payer_members
            WHERE city IN ('Sacramento', 'Atlanta'))
SELECT mm.member_city, f.facility_type,
       (f.city = mm.member_city) AS in_market,
       count(*) AS claims,
       round(sum(c.allowed_amount) / 1e6, 1) AS musd,
       round(avg(c.allowed_amount), 0)       AS avg_allowed
FROM raw.payer_claims c JOIN mm USING (member_id)
JOIN raw.ops_facilities f ON f.facility_id = c.facility_id
GROUP BY 1, 2, 3 ORDER BY 1, musd DESC;

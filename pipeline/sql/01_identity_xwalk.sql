-- marts.identity_xwalk: links ehr.patients to payer.members (no shared key in source).
--
-- Match strategy, in priority order:
--   1. exact  — normalized name (lowercase, accents stripped) + DOB, unique match
--   2. exact-tiebreak — same key, multiple candidates, resolved by zip then gender
--   3. fuzzy  — blocked on DOB + gender, Jaro-Winkler >= 0.92 on full name,
--               gated by (exact last name OR matching zip) to avoid merging
--               different people with similar names (Mitchell vs Miller)
-- A member is never assigned to more than one patient (best match wins).

CREATE OR REPLACE TABLE marts.identity_xwalk AS
WITH p AS (
    SELECT patient_id,
           strip_accents(lower(trim(first_name))) AS fn,
           strip_accents(lower(trim(last_name)))  AS ln,
           dob, gender, zip
    FROM raw.ehr_patients
),
m AS (
    SELECT member_id,
           strip_accents(lower(trim(first_name))) AS fn,
           strip_accents(lower(trim(last_name)))  AS ln,
           dob, gender, zip
    FROM raw.payer_members
),
exact_pairs AS (
    SELECT p.patient_id, m.member_id,
           (p.zip = m.zip)::int    AS zip_ok,
           (p.gender = m.gender)::int AS gender_ok,
           count(*) OVER (PARTITION BY p.patient_id) AS n_cand
    FROM p JOIN m ON p.fn = m.fn AND p.ln = m.ln AND p.dob = m.dob
),
exact_best AS (
    -- unique matches pass through; ambiguous ones only if zip breaks the tie
    SELECT patient_id, member_id,
           CASE WHEN n_cand = 1 THEN 'exact' ELSE 'exact_tiebreak' END AS match_method,
           1.0 AS match_confidence
    FROM exact_pairs
    QUALIFY row_number() OVER (PARTITION BY patient_id
                               ORDER BY zip_ok DESC, gender_ok DESC, member_id) = 1
        AND (n_cand = 1 OR max(zip_ok) OVER (PARTITION BY patient_id) = 1)
),
unmatched AS (
    SELECT * FROM p WHERE patient_id NOT IN (SELECT patient_id FROM exact_best)
),
fuzzy_pairs AS (
    SELECT u.patient_id, m.member_id,
           jaro_winkler_similarity(u.fn || ' ' || u.ln, m.fn || ' ' || m.ln) AS sim
    FROM unmatched u
    JOIN m ON u.dob = m.dob AND u.gender = m.gender
    WHERE jaro_winkler_similarity(u.fn || ' ' || u.ln, m.fn || ' ' || m.ln) >= 0.92
      AND (u.ln = m.ln OR u.zip = m.zip)
),
fuzzy_best AS (
    SELECT patient_id, member_id, 'fuzzy' AS match_method, sim AS match_confidence
    FROM fuzzy_pairs
    QUALIFY row_number() OVER (PARTITION BY patient_id ORDER BY sim DESC, member_id) = 1
),
combined AS (
    SELECT * FROM exact_best
    UNION ALL
    SELECT * FROM fuzzy_best
)
-- enforce 1:1 — if two patients claim the same member, the stronger match wins
SELECT patient_id, member_id, match_method, match_confidence
FROM combined
QUALIFY row_number() OVER (PARTITION BY member_id
                           ORDER BY match_confidence DESC, match_method, patient_id) = 1;

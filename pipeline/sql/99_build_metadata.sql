-- marts._build_metadata — when was this warehouse built, and how stale is it?
--
-- The warehouse is a deliberate materialized cache of read-only Redshift
-- (see docs/decisions/0002-materialization-and-freshness.md). A cache you
-- cannot age is a cache you cannot trust, so every build records its own
-- provenance: build time, row counts, and the newest event date per source.
--
-- Runs last (99_) so it observes the finished build.

CREATE OR REPLACE TABLE marts._build_metadata AS
WITH src AS (
    SELECT 'raw.payer_claims'      AS source_table, count(*) AS row_count,
           max(service_date)::date AS max_event_date, 'service_date' AS event_column,
           'processed_date'        AS incremental_column
    FROM raw.payer_claims
    UNION ALL SELECT 'raw.ehr_encounters', count(*), max(admission_dt)::date,
           'admission_dt', 'admission_dt' FROM raw.ehr_encounters
    UNION ALL SELECT 'raw.ops_appointments', count(*), max(scheduled_dt_local)::date,
           'scheduled_dt_local', 'booked_at' FROM raw.ops_appointments
    UNION ALL SELECT 'raw.ops_referrals', count(*), max(issued_dt)::date,
           'issued_dt', 'issued_dt' FROM raw.ops_referrals
    UNION ALL SELECT 'raw.ops_or_schedule', count(*), max(scheduled_start_dt_local)::date,
           'scheduled_start_dt_local', 'scheduled_start_dt_local' FROM raw.ops_or_schedule
    UNION ALL SELECT 'raw.pharmacy_rx_claims', count(*), max(fill_date)::date,
           'fill_date', 'fill_date' FROM raw.pharmacy_rx_claims
    UNION ALL SELECT 'raw.payer_members', count(*), NULL,
           NULL, 'updated_at' FROM raw.payer_members
)
SELECT current_timestamp                                   AS built_at,
       source_table, row_count, event_column, max_event_date,
       incremental_column,
       date_diff('day', max_event_date, current_date)       AS days_behind_today
FROM src;

"""Step 2a: extract Redshift tables to data/raw/*.parquet.

Full-row extracts for everything analytically useful. Two exceptions:
- ehr.observations (70M rows of vitals/labs): pre-aggregated in Redshift to
  patient x month x observation type — row grain adds nothing for strategy analytics.
- outreach.communications_log (4.6M): skipped; outreach delivery detail is out of
  scope for the strategy use case.

Re-runnable: skips tables whose parquet already exists (delete the file to refresh).
"""

import importlib.util
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

spec = importlib.util.spec_from_file_location(
    "connect_check", Path(__file__).parent / "00_connect_check.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

RAW = Path(__file__).parent.parent / "data" / "raw"
CHUNK_ROWS = 500_000

FULL_TABLES = [
    "payer.members",
    "payer.plans",
    "payer.employers",
    "payer.member_eligibility_history",
    "payer.claims",
    "ehr.patients",
    "ehr.encounters",
    "ehr.conditions",
    "ehr.medications",
    "ehr.procedures",
    "pharmacy.rx_claims",
    "ops.facilities",
    "ops.providers",
    "ops.referrals",
    "ops.appointments",
    "ops.or_schedule",
    "ops.bed_census_daily",
    "outreach.wellness_programs",
    "outreach.program_enrollments",
    "external.census_tract_demographics",
    "external.competitor_facilities",
    "external.drive_time_isochrones",
]

AGG_QUERIES = {
    "ehr.observations_monthly": """
        SELECT patient_id,
               DATE_TRUNC('month', observation_dt)::date AS observation_month,
               observation_loinc,
               MAX(observation_name)                     AS observation_name,
               COUNT(*)                                  AS n_observations,
               AVG(value_numeric)                        AS avg_value_numeric,
               SUM(CASE WHEN abnormal_flag IS NOT NULL
                         AND abnormal_flag NOT IN ('', 'N') THEN 1 ELSE 0 END) AS n_abnormal
        FROM ehr.observations
        GROUP BY 1, 2, 3
    """,
}


def out_path(name: str) -> Path:
    return RAW / (name.replace(".", "_") + ".parquet")


def extract(cur, name: str, query: str) -> None:
    dest = out_path(name)
    if dest.exists():
        print(f"skip {name} (exists)")
        return
    t0 = time.time()
    cur.execute(query)
    writer = None
    total = 0
    tmp = dest.with_suffix(".parquet.tmp")
    while True:
        rows = cur.fetchmany(CHUNK_ROWS)
        if not rows and writer is not None:
            break
        cols = [d[0].decode() if isinstance(d[0], bytes) else d[0] for d in cur.description]
        table = pa.Table.from_pylist([dict(zip(cols, r)) for r in rows])
        if writer is None:
            writer = pq.ParquetWriter(tmp, table.schema, compression="zstd")
        else:
            table = table.cast(writer.schema, safe=False)
        writer.write_table(table)
        total += len(rows)
        if not rows:
            break
    writer.close()
    tmp.rename(dest)
    mb = dest.stat().st_size / 1e6
    print(f"{name}: {total:,} rows, {mb:.1f} MB, {time.time() - t0:.0f}s")


def connect_patient():
    """Own connection with a long socket timeout: big table scans can take
    minutes before Redshift starts streaming rows."""
    import os

    import redshift_connector

    return redshift_connector.connect(
        host=os.environ["host"].strip(),
        port=int(os.environ["port"].strip()),
        database=os.environ["database"].strip(),
        user=os.environ["username"].strip(),
        password=os.environ["password"].strip(),
        ssl=True,
        timeout=600,
    )


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    jobs = [(t, f"SELECT * FROM {t}") for t in FULL_TABLES] + list(AGG_QUERIES.items())
    conn = connect_patient()
    cur = conn.cursor()
    for name, query in jobs:
        try:
            extract(cur, name, query)
        except Exception as e:
            print(f"{name}: FAILED ({e}); reconnecting")
            try:
                conn.close()
            except Exception:
                pass
            conn = connect_patient()
            cur = conn.cursor()
            extract(cur, name, query)
    conn.close()
    print("extract complete")


if __name__ == "__main__":
    main()

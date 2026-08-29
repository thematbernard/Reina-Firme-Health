"""Step 2b: build data/reina_firme.duckdb from data/raw/*.parquet.

Recreates the whole database from scratch each run. Source tables keep their
Redshift schema-qualified names (payer.members, ehr.patients, ...); marts land
in a `marts` schema in later pipeline steps.
"""

from pathlib import Path

import duckdb

DATA = Path(__file__).parent.parent / "data"
RAW = DATA / "raw"
DB = DATA / "reina_firme.duckdb"


def main():
    files = sorted(RAW.glob("*.parquet"))
    if not files:
        raise SystemExit("no parquet files in data/raw — run 02_extract.py first")

    if DB.exists():
        DB.unlink()
    con = duckdb.connect(str(DB))

    for f in files:
        schema, _, table = f.stem.partition("_")
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        con.execute(f'CREATE TABLE "{schema}"."{table}" AS SELECT * FROM read_parquet(\'{f}\')')
        n = con.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"').fetchone()[0]
        print(f"{schema}.{table}: {n:,} rows")

    con.close()
    print(f"\nbuilt {DB} ({DB.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()

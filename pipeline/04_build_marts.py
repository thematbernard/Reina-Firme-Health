"""Step 3: build data/marts.duckdb from the raw parquet extracts.

Kept separate from reina_firme.duckdb (the immutable raw snapshot) so mart
rebuilds never fight viewers over DuckDB's single-writer lock.

Creates:
  raw.*   — views over data/raw/*.parquet (not materialized)
  marts.* — materialized tables, one per SQL file in pipeline/sql/, run in name order
"""

from pathlib import Path

import duckdb

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "warehouse.duckdb"
SQL_DIR = Path(__file__).parent / "sql"


def main():
    if DB.exists():
        DB.unlink()
    con = duckdb.connect(str(DB))
    con.execute("CREATE SCHEMA raw")
    con.execute("CREATE SCHEMA marts")

    for f in sorted(RAW.glob("*.parquet")):
        con.execute(f"CREATE VIEW raw.{f.stem} AS SELECT * FROM read_parquet('{f}')")

    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        con.execute(sql_file.read_text())
        print(f"ran {sql_file.name}")

    for (table,) in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='marts' ORDER BY 1"
    ).fetchall():
        n = con.execute(f"SELECT count(*) FROM marts.{table}").fetchone()[0]
        print(f"  marts.{table}: {n:,} rows")

    con.close()
    print(f"built {DB}")


if __name__ == "__main__":
    main()

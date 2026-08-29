"""Step 6: export a small, self-contained, PII-free warehouse.

Why: today the repo cannot be run without Redshift credentials and a ~1 hour
extract. That is a real barrier for a reviewer who just wants to try the MCP
server. The marts are aggregates — 7 MB fully materialized — so they travel.

What this is NOT: the full warehouse. `raw.*` carries member names, DOB, email,
phone and addresses for 1.1M members and is 2.1 GB materialized. It must never
be exported. The PII guard below enforces that rather than trusting the author
to remember it.

The MCP server prefers data/warehouse.duckdb when present and falls back to this
artifact, so a clone with no source access still serves the marts.

Run:  make portable
"""

import os
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent.parent
SRC = ROOT / "data" / "warehouse.duckdb"
OUT_DIR = ROOT / "data" / "portable"
OUT = OUT_DIR / "reina_marts.duckdb"

# Column names that must never appear in an exported artifact. Substring match,
# deliberately broad — a false positive costs one line of review, a false
# negative ships identifiable data.
PII_TOKENS = (
    "first_name", "last_name", "dob", "birth", "email", "phone", "ssn",
    "mrn", "address", "member_name", "patient_name",
)
# Business names are not personal names; allow the specific known-safe columns.
PII_ALLOWLIST = {"facility_name"}


def pii_columns(con) -> list[tuple[str, str]]:
    rows = con.execute(
        """SELECT table_name, column_name FROM information_schema.columns
           WHERE table_schema = 'marts'"""
    ).fetchall()
    return [
        (t, c) for t, c in rows
        if c not in PII_ALLOWLIST and any(tok in c.lower() for tok in PII_TOKENS)
    ]


def main():
    if not SRC.exists():
        raise SystemExit(f"{SRC} not found — run `make marts` first")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".duckdb.tmp")
    tmp.unlink(missing_ok=True)

    con = duckdb.connect(str(tmp))
    try:
        con.execute(f"ATTACH '{SRC}' AS src (READ_ONLY)")
        tables = [
            t for (t,) in con.execute(
                "SELECT table_name FROM duckdb_tables() "
                "WHERE database_name = 'src' AND schema_name = 'marts' ORDER BY 1"
            ).fetchall()
        ]
        if not tables:
            raise SystemExit("no marts found in source — run `make marts`")

        con.execute("CREATE SCHEMA marts")
        for t in tables:
            con.execute(f'CREATE TABLE marts."{t}" AS SELECT * FROM src.marts."{t}"')
            n = con.execute(f'SELECT count(*) FROM marts."{t}"').fetchone()[0]
            print(f"  marts.{t}: {n:,} rows")

        con.execute("DETACH src")

        leaks = pii_columns(con)
        if leaks:
            raise SystemExit(
                "REFUSING TO EXPORT — PII-shaped columns found:\n"
                + "\n".join(f"  marts.{t}.{c}" for t, c in leaks)
                + "\nAdd to PII_ALLOWLIST only if the column is genuinely "
                  "non-personal (e.g. a facility name)."
            )
        print(f"  PII guard: clean ({len(PII_TOKENS)} tokens checked)")
    finally:
        con.close()

    tmp.replace(OUT)
    mb = OUT.stat().st_size / 1e6
    print(f"\nwrote {OUT} ({mb:.1f} MB)")
    print("\nThis artifact is client-derived data. It is gitignored by default.")
    print("Before committing or sharing it, confirm with the data owner. To")
    print("commit it, remove the exclusion in .gitignore.")
    if mb > 100:
        print("\nWARNING larger than 100 MB — GitHub will reject it; use a release asset")
        sys.exit(1)


if __name__ == "__main__":
    main()

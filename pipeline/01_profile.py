"""Phase 1 profiling: dump schema (columns/types) and date ranges to docs/data-notes.md."""

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "connect_check", Path(__file__).parent / "00_connect_check.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

OUT = Path(__file__).parent.parent / "docs" / "data-notes.md"

conn = mod.connect()
cur = conn.cursor()

cur.execute(
    """
    SELECT table_schema, table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_internal', 'pg_auto_copy')
    ORDER BY table_schema, table_name, ordinal_position
    """
)
cols = cur.fetchall()

tables = {}
for schema, table, col, dtype in cols:
    tables.setdefault((schema, table), []).append((col, dtype))

lines = ["# Data notes — Reina Firme Redshift\n"]
lines.append(f"{len(tables)} tables. Schemas: " + ", ".join(sorted({s for s, _ in tables})) + "\n")

for (schema, table), columns in sorted(tables.items()):
    lines.append(f"\n## {schema}.{table}\n")
    lines.append("| column | type | notes |")
    lines.append("|---|---|---|")
    for col, dtype in columns:
        lines.append(f"| {col} | {dtype} | |")

    # date range for the first date/timestamp column, as a freshness signal
    date_cols = [c for c, d in columns if d in ("date", "timestamp without time zone", "timestamp with time zone")]
    if date_cols:
        dc = date_cols[0]
        try:
            cur.execute(f'SELECT MIN("{dc}"), MAX("{dc}") FROM "{schema}"."{table}"')
            lo, hi = cur.fetchone()
            lines.append(f"\nDate range ({dc}): {lo} → {hi}")
        except Exception as e:
            conn.rollback()
            lines.append(f"\nDate range ({dc}): query failed ({e})")

OUT.parent.mkdir(exist_ok=True)
OUT.write_text("\n".join(lines) + "\n")
print(f"wrote {OUT} ({len(tables)} tables, {len(cols)} columns)")
conn.close()

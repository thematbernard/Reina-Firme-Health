"""Step 5: generate semantic/schema.md from the built warehouse.

The schema half of the semantic layer is GENERATED, never hand-written. An
earlier hand-written version claimed columns that did not exist
(ops_facilities.name, ops_appointments.patient_id), and the MCP agent trusted
it and emitted broken SQL. Generating it means the agent's column list cannot
disagree with the warehouse.

Hand-written semantics (metric definitions, caveats, business rules) live in
semantic/dictionary.md and are NOT touched here.

Emits per table: real row count, every column with type, observed min/max for
each date/timestamp column (this is where the time-window caveat comes from),
plus the canonical join paths from semantic/joins.json with measured orphan
counts.

Run:  uv run pipeline/05_gen_schema_doc.py   (or `make docs`)
      --check  exit 1 if the file on disk is stale (used by tests/CI)
"""

import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "warehouse.duckdb"
JOINS = ROOT / "semantic" / "joins.json"
OUT = ROOT / "semantic" / "schema.md"

TEMPORAL = ("DATE", "TIMESTAMP")


def human(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def render(con) -> str:
    tables = con.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('raw', 'marts')
        ORDER BY table_schema DESC, table_name
        """
    ).fetchall()

    out = [
        "# Reina Firme — Schema Reference (GENERATED)",
        "",
        "**Do not edit by hand.** Regenerate with `make docs`",
        "(`pipeline/05_gen_schema_doc.py`). `tests/test_warehouse.py` fails if this",
        "file is stale, so the column lists below always match the warehouse.",
        "",
        "Business meaning, metric definitions and data-quality caveats are in",
        "`semantic/dictionary.md` — read that first.",
        "",
        "Local naming: Redshift's `payer.claims` is `raw.payer_claims`",
        "(`raw.<source_schema>_<table>`); derived tables are `marts.<table>`.",
        "",
        "## Tables",
        "",
    ]

    for schema, table in tables:
        fq = f"{schema}.{table}"
        n = con.execute(f"SELECT count(*) FROM {fq}").fetchone()[0]
        cols = con.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            [schema, table],
        ).fetchall()

        out.append(f"### {fq} — {n:,} rows ({human(n)})")
        out.append("")
        out.append("| column | type | notes |")
        out.append("|---|---|---|")
        for col, dtype in cols:
            note = ""
            if any(t in dtype.upper() for t in TEMPORAL) and n:
                lo, hi, nulls = con.execute(
                    f'SELECT min("{col}"), max("{col}"), count(*) - count("{col}") FROM {fq}'
                ).fetchone()
                if lo is not None:
                    note = f"range {str(lo)[:10]} → {str(hi)[:10]}"
                if nulls:
                    note += f"{'; ' if note else ''}{100.0 * nulls / n:.0f}% null"
            out.append(f"| `{col}` | {dtype} | {note} |")
        out.append("")

    out += ["## Canonical join paths", "",
            "Every path below is asserted by `tests/test_warehouse.py` to execute with",
            "zero orphan keys. Source of truth: `semantic/joins.json`.", "",
            "| from | to | orphans | notes |", "|---|---|---|---|"]

    for j in json.loads(JOINS.read_text())["joins"]:
        lt, lc, rt, rc = j["left"], j["left_col"], j["right"], j["right_col"]
        nonnull, orphans = con.execute(
            f"""SELECT count("{lc}"),
                       count(*) FILTER (WHERE "{lc}" IS NOT NULL
                         AND "{lc}" NOT IN (SELECT "{rc}" FROM {rt}))
                FROM {lt}"""
        ).fetchone()
        total = con.execute(f"SELECT count(*) FROM {lt}").fetchone()[0]
        notes = [j["note"]] if j.get("note") else []
        if total and nonnull < total:
            notes.insert(0, f"{100.0 * (total - nonnull) / total:.0f}% null")
        out.append(f"| `{lt}.{lc}` | `{rt}.{rc}` | {orphans:,} | {'; '.join(notes)} |")

    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if schema.md is stale")
    args = ap.parse_args()

    if not DB.exists():
        raise SystemExit(f"{DB} not found — run `make marts` first")

    con = duckdb.connect(str(DB), read_only=True)
    try:
        content = render(con)
    finally:
        con.close()

    if args.check:
        if not OUT.exists():
            print(f"FAIL {OUT} does not exist — run `make docs`")
            sys.exit(1)
        if OUT.read_text() != content:
            print(f"FAIL {OUT} is stale — run `make docs`")
            sys.exit(1)
        print(f"ok {OUT} is current")
        return

    OUT.write_text(content)
    print(f"wrote {OUT} ({len(content.splitlines())} lines)")


if __name__ == "__main__":
    main()

"""MCP server: LLM-queryable analytics over the Reina Firme local warehouse.

Exposes read-only SQL access to data/warehouse.duckdb plus the semantic layer
(semantic/dictionary.md) so the model uses Reina Firme's canonical table map
and metric definitions instead of inventing its own.

Run:  uv run mcp_server/server.py   (stdio transport)
"""

import argparse
import hashlib
import os
import re
from pathlib import Path

import duckdb
from mcp.server.mcpserver import MCPServer

ROOT = Path(__file__).parent.parent
DICTIONARY = ROOT / "semantic" / "dictionary.md"
SCHEMA = ROOT / "semantic" / "schema.md"
FULL_DB = ROOT / "data" / "warehouse.duckdb"
PORTABLE_DB = ROOT / "data" / "portable" / "reina_marts.duckdb"


def resolve_db() -> Path:
    """Pick a warehouse, preferring the locally built one.

    data/warehouse.duckdb        — raw.* views over parquet, plus marts.
    data/portable/reina_marts.duckdb — marts only, 7 MB, PII-free. Lets a clone
                                   with no Redshift access still serve the marts.
    REINA_DB overrides both.
    """
    if env := os.environ.get("REINA_DB"):
        return Path(env)
    if FULL_DB.exists():
        return FULL_DB
    if PORTABLE_DB.exists():
        return PORTABLE_DB
    raise SystemExit(
        f"no warehouse found. Expected {FULL_DB} (run `make build`) or "
        f"{PORTABLE_DB} (run `make portable`), or set REINA_DB."
    )


def detect_mode(db: Path) -> str:
    """Determine capability from the DATA, not from which path was chosen.

    A REINA_DB override pointing at a marts-only file must still announce
    marts-only, or the agent spends the session guessing at absent raw.* tables.
    """
    con = duckdb.connect(str(db), read_only=True)
    try:
        n_raw = con.execute(
            "SELECT count(*) FROM (SELECT 1 FROM duckdb_tables() WHERE schema_name='raw' "
            "UNION ALL SELECT 1 FROM duckdb_views() WHERE schema_name='raw')"
        ).fetchone()[0]
    finally:
        con.close()
    return "full" if n_raw else "portable"


DB = resolve_db()
DB_MODE = detect_mode(DB)

MARTS_ONLY_NOTICE = (
    "\n\n> **THIS SERVER IS RUNNING MARTS-ONLY.** Only `marts.*` tables exist; "
    "every `raw.*` table described below is UNAVAILABLE here. Answer from "
    "`marts.facility_metrics`, `marts.market_summary` and "
    "`marts.identity_xwalk`, and say so plainly if a question needs row-level "
    "detail the marts do not carry. Call `list_tables` to see what is present.\n"
)

MAX_ROWS = 500
ALLOWED_START = re.compile(r"^\s*(WITH|SELECT|DESCRIBE|SHOW|SUMMARIZE|EXPLAIN)\b", re.IGNORECASE)


def build_fingerprint() -> str:
    """Short hash of the code and semantic layer this process actually loaded.

    MCP servers are started once by the client and live for the whole session,
    so an editor-side change does not reach a running server. A session was
    silently served a dictionary predating several corrections, and it was only
    caught by accident. Surfacing the fingerprint in `instructions` means any
    client can compare what it is running against the repo.
    """
    h = hashlib.sha256()
    for f in (Path(__file__), DICTIONARY, SCHEMA):
        h.update(f.read_bytes() if f.exists() else b"missing")
    return h.hexdigest()[:12]

mcp = MCPServer(
    "reina-firme-analytics",
    instructions=(
        "Analytics warehouse for Reina Firme Health (integrated payer+provider). "
        "ALWAYS call get_data_dictionary first: it contains the generated column "
        "reference, canonical metric definitions, join paths, and measured "
        "data-quality caveats you must follow. Do not guess column names. "
        f"[build {build_fingerprint()}] — if this does not match the repo's "
        "`make fingerprint`, this server is running stale code; restart the client. "
        + ("MODE: marts-only — raw.* tables are NOT available in this deployment; "
           "answer from marts.* and say so when a question needs detail they do "
           "not carry." if DB_MODE == "portable" else "MODE: full warehouse.")
    ),
)


def _connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB), read_only=True)


def _format(cols, rows, truncated: bool) -> str:
    def cell(v):
        s = "" if v is None else str(v)
        return s[:120] + "…" if len(s) > 120 else s

    lines = ["\t".join(cols)]
    lines += ["\t".join(cell(v) for v in r) for r in rows]
    out = "\n".join(lines)
    if truncated:
        out += f"\n[truncated at {MAX_ROWS} rows — add aggregation or LIMIT]"
    return out


@mcp.tool()
def get_data_dictionary() -> str:
    """The semantic layer, in two parts: hand-written business rules (identity,
    time windows, canonical metric definitions, measured data-quality caveats)
    followed by the GENERATED schema reference (every table's real columns,
    types, date ranges and join paths). Read this before writing any SQL — the
    column names here are generated from the warehouse, so trust them over
    anything you remember."""
    body = DICTIONARY.read_text() + "\n\n---\n\n" + SCHEMA.read_text()
    if DB_MODE == "portable":
        return MARTS_ONLY_NOTICE + body
    return body


@mcp.tool()
def list_tables() -> str:
    """List all queryable tables (schema.table) with row counts."""
    con = _connect()
    rows = con.execute(
        """
        SELECT schema_name || '.' || table_name AS tbl,
               coalesce(estimated_size, 0) AS approx_rows
        FROM duckdb_tables()
        UNION ALL
        SELECT schema_name || '.' || view_name, NULL
        FROM duckdb_views() WHERE schema_name IN ('raw', 'marts')
        ORDER BY 1
        """
    ).fetchall()
    con.close()
    return "\n".join(f"{t}\t{'' if n is None else n}" for t, n in rows)


@mcp.tool()
def describe_table(table: str) -> str:
    """Columns and types for one table, plus 3 sample rows. `table` must be
    schema-qualified, e.g. 'raw.payer_claims' or 'marts.identity_xwalk'."""
    if not re.fullmatch(r"[a-z_]+\.[a-z_0-9]+", table):
        return "error: table must look like 'raw.payer_claims'"
    con = _connect()
    try:
        schema = con.execute(f"DESCRIBE {table}").fetchall()
        cols = [r[0] for r in schema]
        sample = con.execute(f"SELECT * FROM {table} LIMIT 3").fetchall()
    except Exception as e:
        return f"error: {e}"
    finally:
        con.close()
    head = "\n".join(f"{r[0]}\t{r[1]}" for r in schema)
    return f"columns:\n{head}\n\nsample:\n{_format(cols, sample, False)}"


@mcp.tool()
def run_query(sql: str) -> str:
    """Run a read-only SQL query (DuckDB dialect) and return rows as TSV
    (capped at 500 — aggregate rather than paginate). Consult get_data_dictionary
    for table names, join paths, and canonical metric definitions first."""
    if not ALLOWED_START.match(sql):
        return "error: only SELECT/WITH/DESCRIBE/SHOW/SUMMARIZE/EXPLAIN queries are allowed"
    if ";" in sql.rstrip().rstrip(";"):
        return "error: a single statement per call"
    con = _connect()
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)
    except Exception as e:
        return f"error: {e}"
    finally:
        con.close()
    return _format(cols, rows[:MAX_ROWS], truncated=len(rows) > MAX_ROWS)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--transport", default="stdio", choices=["stdio", "sse", "streamable-http"],
        help="stdio for a local client (default); streamable-http to host it",
    )
    ap.add_argument("--host", default="127.0.0.1", help="bind host for http transports")
    ap.add_argument("--port", type=int, default=8000, help="bind port for http transports")
    args = ap.parse_args()

    if args.transport == "stdio":
        mcp.run()
    else:
        # NOTE before exposing this publicly: run_query accepts arbitrary
        # read-only SQL with no statement timeout, so one cartesian join can
        # exhaust the box. Hosting needs auth, a statement timeout, a memory cap
        # and rate limiting first — see docs/roadmap.md.
        mcp.run(transport=args.transport, host=args.host, port=args.port)

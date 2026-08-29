"""MCP server: LLM-queryable analytics over the Reina Firme local warehouse.

Exposes read-only SQL access to data/warehouse.duckdb plus the semantic layer
(semantic/dictionary.md) so the model uses Reina Firme's canonical table map
and metric definitions instead of inventing its own.

Run:  uv run mcp_server/server.py   (stdio transport)
"""

import re
from pathlib import Path

import duckdb
from mcp.server.mcpserver import MCPServer

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "warehouse.duckdb"
DICTIONARY = ROOT / "semantic" / "dictionary.md"

MAX_ROWS = 500
ALLOWED_START = re.compile(r"^\s*(WITH|SELECT|DESCRIBE|SHOW|SUMMARIZE|EXPLAIN)\b", re.IGNORECASE)

mcp = MCPServer(
    "reina-firme-analytics",
    instructions=(
        "Analytics warehouse for Reina Firme Health (integrated payer+provider). "
        "ALWAYS call get_data_dictionary first: it contains the table map, canonical "
        "metric definitions, join paths, and time-window caveats you must follow."
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
    """The semantic layer: full table map, canonical metric definitions (utilization,
    leakage), join paths, and time-window caveats. Read this before writing any SQL."""
    return DICTIONARY.read_text()


@mcp.tool()
def list_tables() -> str:
    """List all queryable tables (schema.table) with row counts."""
    con = _connect()
    rows = con.execute(
        """
        SELECT table_schema || '.' || table_name AS tbl,
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
    mcp.run()

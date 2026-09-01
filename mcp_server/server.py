"""MCP server: LLM-queryable analytics over the Reina Firme local warehouse.

Exposes read-only SQL access to data/warehouse.duckdb plus the semantic layer
(semantic/dictionary.md) so the model uses Reina Firme's canonical table map
and metric definitions instead of inventing its own.

Run:  uv run mcp_server/server.py   (stdio transport)
"""

import argparse
import hashlib
import logging
import os
import re
import sys
from pathlib import Path

import duckdb
from mcp.server.mcpserver import MCPServer

# Diagnostics go to stderr, never stdout: on the stdio transport stdout carries
# the JSON-RPC frames, and a single stray byte there desynchronises the client.
log = logging.getLogger(__name__)

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


def sql_code_only(sql: str) -> str:
    r"""Blank out comments, string literals and quoted identifiers, keeping length.

    The guardrails below need to reason about SQL *structure*, and both were
    reading the raw text instead:

    - a query opening with a `-- comment` line failed ALLOWED_START, which is
      exactly how a model writes a non-trivial query;
    - a `;` inside a string literal tripped the single-statement check.

    Replacing those spans with spaces (rather than deleting them) keeps offsets
    intact, so `^\s*` still anchors correctly. Only this copy is inspected —
    the original text is what gets executed, so nothing is silently rewritten.

    Escaping follows DuckDB: quotes are doubled, backslash is not an escape.
    Dollar-quoted strings are not tracked, so a `;` inside one is still
    rejected — conservative in the safe direction.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        pair, ch = sql[i:i + 2], sql[i]
        if pair == "--":
            j = sql.find("\n", i)
            j = n if j == -1 else j
        elif pair == "/*":
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
        elif ch in "'\"":
            j = i + 1
            while j < n:
                if sql[j] != ch:
                    j += 1
                elif sql[j:j + 2] == ch * 2:  # doubled quote = literal quote
                    j += 2
                else:
                    j += 1
                    break
        else:
            out.append(ch)
            i += 1
            continue
        out.append(" " * (j - i))
        i = j
    return "".join(out)


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


def _oneline(sql: str, limit: int = 300) -> str:
    """Collapse SQL to one log line — multi-line SQL in stderr is unreadable."""
    flat = " ".join(sql.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


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
    log.info("get_data_dictionary (mode=%s)", DB_MODE)
    body = DICTIONARY.read_text() + "\n\n---\n\n" + SCHEMA.read_text()
    if DB_MODE == "portable":
        return MARTS_ONLY_NOTICE + body
    return body


@mcp.tool()
def list_tables() -> str:
    """List all queryable tables (schema.table) with approximate row counts.
    Counts are DuckDB estimates, not exact. Views over parquet store no size,
    so they report `view` rather than a number — that means "count unknown",
    NOT empty; the view is queryable like any table. SELECT count(*) if you
    need an exact figure."""
    log.info("list_tables")
    con = _connect()
    rows = con.execute(
        """
        SELECT schema_name || '.' || table_name AS tbl,
               coalesce(estimated_size, 0)::VARCHAR AS approx_rows
        FROM duckdb_tables()
        UNION ALL
        SELECT schema_name || '.' || view_name, 'view'
        FROM duckdb_views() WHERE schema_name IN ('raw', 'marts')
        ORDER BY 1
        """
    ).fetchall()
    con.close()
    header = "table\tapprox_rows ('view' = count not stored, still queryable)"
    return "\n".join([header] + [f"{t}\t{n}" for t, n in rows])


@mcp.tool()
def describe_table(table: str) -> str:
    """Columns and types for one table, plus 3 sample rows. `table` must be
    schema-qualified, e.g. 'raw.payer_claims' or 'marts.identity_xwalk'."""
    log.info("describe_table: %s", table)
    if not re.fullmatch(r"[a-z_]+\.[a-z_0-9]+", table):
        log.warning("describe_table rejected malformed name: %r", table)
        return "error: table must look like 'raw.payer_claims'"
    con = _connect()
    try:
        schema = con.execute(f"DESCRIBE {table}").fetchall()
        cols = [r[0] for r in schema]
        sample = con.execute(f"SELECT * FROM {table} LIMIT 3").fetchall()
    except Exception as e:
        log.warning("describe_table failed for %s: %s", table, e)
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
    code = sql_code_only(sql)
    if not ALLOWED_START.match(code):
        log.warning("run_query rejected (not a read statement): %s", _oneline(sql))
        return "error: only SELECT/WITH/DESCRIBE/SHOW/SUMMARIZE/EXPLAIN queries are allowed"
    if ";" in code.rstrip().rstrip(";"):
        log.warning("run_query rejected (multiple statements): %s", _oneline(sql))
        return "error: a single statement per call"
    log.info("run_query: %s", _oneline(sql))
    con = _connect()
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)
    except Exception as e:
        # The model sees this and usually self-corrects; log it so a demo-time
        # wrong answer can be traced back to the query that produced it.
        log.warning("run_query failed: %s — sql: %s", e, _oneline(sql))
        return f"error: {e}"
    finally:
        con.close()
    log.info("run_query returned %d rows", min(len(rows), MAX_ROWS))
    return _format(cols, rows[:MAX_ROWS], truncated=len(rows) > MAX_ROWS)


def build_log_handlers() -> list[logging.Handler]:
    """stderr always; REINA_LOG_FILE adds a file a second pane can `tail -f`.

    Why a file at all, when everything already goes to stderr: a client is not
    obliged to drain the child's stderr, and Claude Code only does so during the
    connection handshake. Measured — the startup line below reaches the client's
    MCP log, and not one per-tool line after it does. So on stdio the SQL log is
    written and then discarded, which is the worst of both. A file handler makes
    the same records observable without changing transport.

    Failure to open is fatal rather than silent: the whole point of this handler
    is that logs stop vanishing.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if path := os.environ.get("REINA_LOG_FILE"):
        try:
            handlers.append(logging.FileHandler(path, encoding="utf-8"))
        except OSError as e:
            raise SystemExit(f"REINA_LOG_FILE={path!r} is not writable: {e}")
    return handlers


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--transport", default="stdio", choices=["stdio", "sse", "streamable-http"],
        help="stdio for a local client (default); streamable-http to host it",
    )
    ap.add_argument("--host", default="127.0.0.1", help="bind host for http transports")
    ap.add_argument("--port", type=int, default=8000, help="bind port for http transports")
    args = ap.parse_args()

    # Configure only under __main__: importing this module (tests, probe.py)
    # must not reconfigure the host process's logging.
    # force=True is load-bearing: importing the MCP SDK installs a root
    # StreamHandler, and basicConfig is a no-op when the root logger already has
    # one. Without it this call silently did nothing — no timestamps, and
    # REINA_LOG_LEVEL/REINA_LOG_FILE both ignored.
    logging.basicConfig(
        level=os.environ.get("REINA_LOG_LEVEL", "INFO").upper(),
        handlers=build_log_handlers(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    # Uvicorn logs one access line per JSON-RPC POST — five per tool call, all
    # "POST /mcp 200". That carries nothing the per-tool log lines below don't,
    # and it buries them. The stdio transport has no access log at all, so
    # dropping it also makes the two transports' stderr directly comparable.
    #
    # A filter rather than setLevel: uvicorn.Config applies its own dictConfig
    # at startup, which resets this logger's level and handlers but leaves
    # filters attached. setLevel here is silently undone.
    # REINA_LOG_LEVEL=DEBUG keeps the access log.
    if os.environ.get("REINA_LOG_LEVEL", "INFO").upper() != "DEBUG":
        logging.getLogger("uvicorn.access").addFilter(lambda _record: False)

    log.info(
        "starting reina-firme-analytics: db=%s mode=%s build=%s transport=%s",
        DB, DB_MODE, build_fingerprint(), args.transport,
    )

    if args.transport == "stdio":
        mcp.run()
    else:
        # NOTE before exposing this publicly. Two separate problems:
        #
        # 1. Resource exhaustion — run_query accepts arbitrary SQL with no
        #    statement timeout, so one cartesian join can exhaust the box.
        #    Needs auth, a statement timeout, a memory cap and rate limiting.
        #
        # 2. File disclosure — `read_only=True` blocks writes, not reads of the
        #    local filesystem. read_csv / read_parquet / read_text / glob are
        #    all reachable from a bare SELECT, so a caller could read anything
        #    this process can, including .env. Locally over stdio that is no
        #    worse than the user's own shell; over HTTP it is exfiltration.
        #    Needs enable_external_access=false or a function allowlist —
        #    auth alone does not cover it.
        #
        # See docs/roadmap.md.
        mcp.run(transport=args.transport, host=args.host, port=args.port)

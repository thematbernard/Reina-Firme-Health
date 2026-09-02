"""Connectivity smoke test: list schemas, tables, and row counts.

    --warm   connect and run one trivial query, nothing else. For pre-flight:
             Redshift Serverless auto-pauses, and the first call after an idle
             period pays a resume that a short timeout will not survive. Warming
             deliberately moves that cost off the demo path.

Reads credentials from .env (keys: host, port, database, username, password).
Never prints credential values.
"""

import argparse
import os
import time

import redshift_connector
from dotenv import load_dotenv

load_dotenv()


def connect():
    """Connect, retrying once on failure.

    Redshift Serverless auto-pauses when idle and takes longer to resume than a
    short socket timeout allows, so the first call after a quiet period fails
    and the second succeeds. Measured 2026-09-01: this timed out at 20s, then
    completed on retry. One retry — a second failure is not a cold start.
    """
    last = None
    for attempt in (1, 2):
        try:
            return redshift_connector.connect(
                host=os.environ["host"].strip(),
                port=int(os.environ["port"].strip()),
                database=os.environ["database"].strip(),
                user=os.environ["username"].strip(),
                password=os.environ["password"].strip(),
                ssl=True,
                timeout=120,
            )
        except Exception as e:
            last = e
            print(f"  connect attempt {attempt}/2 failed ({type(e).__name__}); "
                  "the source may be resuming from idle")
    raise last


def warm():
    """Wake the workgroup and report what it cost.

    Prints the elapsed time because that number is the point: a cold resume
    reads as tens of seconds, a warm one as well under two. Seeing which you got
    tells you whether the next query will stall.
    """
    t0 = time.monotonic()
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
    finally:
        conn.close()
    elapsed = time.monotonic() - t0
    state = "was already warm" if elapsed < 2.0 else "resumed from idle"
    print(f"source ready in {elapsed:.1f}s ({state})")
    if elapsed >= 2.0:
        print("  run this again to confirm it stays warm before you present")


def main():
    conn = connect()
    cur = conn.cursor()

    cur.execute("SELECT current_database(), current_user, version()")
    db, user, version = cur.fetchone()
    print(f"connected: db={db} user={user}")
    print(f"server: {version[:80]}")

    cur.execute(
        """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_internal')
        ORDER BY table_schema, table_name
        """
    )
    tables = cur.fetchall()
    print(f"\n{len(tables)} tables/views:")
    for schema, name, ttype in tables:
        print(f"  {schema}.{name} ({ttype})")

    print("\nrow counts:")
    for schema, name, ttype in tables:
        if ttype != "BASE TABLE":
            continue
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{name}"')
            print(f"  {schema}.{name}: {cur.fetchone()[0]:,}")
        except Exception as e:
            print(f"  {schema}.{name}: count failed ({e})")

    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--warm", action="store_true",
                    help="connect and run one trivial query, then exit")
    warm() if ap.parse_args().warm else main()

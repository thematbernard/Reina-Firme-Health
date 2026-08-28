"""Connectivity smoke test: list schemas, tables, and row counts.

Reads credentials from .env (keys: host, port, database, username, password).
Never prints credential values.
"""

import os

import redshift_connector
from dotenv import load_dotenv

load_dotenv()


def connect():
    return redshift_connector.connect(
        host=os.environ["host"].strip(),
        port=int(os.environ["port"].strip()),
        database=os.environ["database"].strip(),
        user=os.environ["username"].strip(),
        password=os.environ["password"].strip(),
        ssl=True,
        timeout=20,
    )


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
    main()

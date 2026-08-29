"""Re-run the analysis SQL files and print every block, so each number in the
accompanying .md can be checked against a live warehouse.

Run:  make analysis        (or: uv run python analysis/run.py [file.sql ...])
"""

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "warehouse.duckdb"


def run(con, path: Path) -> None:
    print(f"\n{'=' * 70}\n{path.name}\n{'=' * 70}")
    for i, st in enumerate(duckdb.extract_statements(path.read_text()), 1):
        q = st.query.strip()
        if not q:
            continue
        cur = con.execute(q)
        if cur.description is None:
            continue
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        if not rows:
            continue
        print(f"\n--- block {i} ---")
        print(" | ".join(cols))
        for r in rows:
            print(" | ".join("" if v is None else str(v) for v in r))


def main():
    files = [Path(a) for a in sys.argv[1:]] or sorted((ROOT / "analysis").glob("*.sql"))
    con = duckdb.connect(str(DB), read_only=True)
    try:
        for f in files:
            run(con, f)
    finally:
        con.close()


if __name__ == "__main__":
    main()

"""Measure the identity crosswalk instead of asserting it.

"87% of patients linked" is COVERAGE, not quality. It says nothing about whether
those links are right, or which real links were missed. This script produces
both numbers.

PRECISION — held-out attribute agreement.
  The matcher uses first/last name, DOB, gender and zip. It never looks at
  address_line1, city, or the PCP fields. For a true link those should agree at
  the same rate they agree for exact matches; for a false link, at the random
  rate. That gives a ceiling (exact), a floor (random pairs) and an estimator:

      precision = (observed - floor) / (ceiling - floor)

  Three independent signals are triangulated so no single one carries the claim.

RECALL — held-out corruption.
  Take patients that currently match exactly (so the answer is known), corrupt
  the patient record the way real data is corrupt (typos, transposed DOB, missing
  zip, marriage name change), re-run the REAL matcher, and check whether the
  correct member comes back. Reported per corruption type, because the failure
  modes are not equally likely and not equally fixable.

The matcher is not reimplemented here: pipeline/sql/01_identity_xwalk.sql is
read from disk and retargeted by substitution, so this cannot drift from the
logic actually shipped.

Run:  make identity-quality
"""

import argparse
import re
import shutil
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "warehouse.duckdb"
MATCHER_SQL = ROOT / "pipeline" / "sql" / "01_identity_xwalk.sql"

# (name, SQL expression producing the corrupted patient row)
CORRUPTIONS = {
    "lastname_typo": """
        first_name,
        CASE WHEN length(last_name) >= 4
             THEN substr(last_name, 1, 1) || substr(last_name, 3, 1)
                  || substr(last_name, 2, 1) || substr(last_name, 4)
             ELSE last_name END AS last_name,
        dob, gender, zip""",
    "firstname_typo": """
        CASE WHEN length(first_name) >= 4
             THEN substr(first_name, 1, 1) || substr(first_name, 3, 1)
                  || substr(first_name, 2, 1) || substr(first_name, 4)
             ELSE first_name END AS first_name,
        last_name, dob, gender, zip""",
    "married_name": """
        first_name, last_name || '-REYES' AS last_name, dob, gender, zip""",
    "dob_day_transposed": """
        first_name, last_name,
        CASE WHEN day(dob) BETWEEN 1 AND 12 THEN make_date(year(dob), day(dob), month(dob))
             ELSE dob + INTERVAL 1 DAY END AS dob,
        gender, zip""",
    "zip_missing": """
        first_name, last_name, dob, gender, CAST(NULL AS VARCHAR) AS zip""",
    "typo_and_zip_missing": """
        first_name,
        CASE WHEN length(last_name) >= 4
             THEN substr(last_name, 1, 1) || substr(last_name, 3, 1)
                  || substr(last_name, 2, 1) || substr(last_name, 4)
             ELSE last_name END AS last_name,
        dob, gender, CAST(NULL AS VARCHAR) AS zip""",
}


def retarget_matcher(patients_table: str, target_table: str) -> str:
    """Rewrite the shipped matcher to read a different patient source and write
    to a scratch table. Fails loudly if the expected anchors are missing, so a
    refactor of the matcher can never silently no-op this measurement."""
    sql = MATCHER_SQL.read_text()
    for anchor, repl in (
        ("CREATE OR REPLACE TABLE marts.identity_xwalk AS",
         f"CREATE OR REPLACE TABLE {target_table} AS"),
        ("FROM raw.ehr_patients", f"FROM {patients_table}"),
    ):
        if sql.count(anchor) != 1:
            raise SystemExit(
                f"matcher SQL no longer contains exactly one {anchor!r} — "
                "update evals/identity_quality.py to match"
            )
        sql = sql.replace(anchor, repl)
    return sql


def measure_precision(con) -> dict:
    rows = con.execute(
        """
        WITH pairs AS (
            SELECT patient_id, member_id, match_method FROM marts.identity_xwalk
            UNION ALL
            SELECT p.patient_id, m.member_id, 'random_control'
            FROM (SELECT patient_id, row_number() OVER (ORDER BY hash(patient_id)) rn
                  FROM raw.ehr_patients LIMIT 20000) p
            JOIN (SELECT member_id, row_number() OVER (ORDER BY hash(member_id)) rn
                  FROM raw.payer_members LIMIT 20000) m USING (rn)
        )
        SELECT x.match_method, count(*) AS n,
               100.0 * avg(CASE WHEN lower(trim(p.address_line1))
                                   = lower(trim(m.address_line1)) THEN 1 ELSE 0 END) AS addr,
               100.0 * avg(CASE WHEN p.city = m.city THEN 1 ELSE 0 END)              AS city,
               100.0 * avg(CASE WHEN p.primary_provider_id
                                   = m.primary_pcp_provider_id THEN 1 ELSE 0 END)    AS pcp
        FROM pairs x
        JOIN raw.ehr_patients p USING (patient_id)
        JOIN raw.payer_members m USING (member_id)
        GROUP BY 1
        """
    ).fetchall()
    by = {r[0]: {"n": r[1], "addr": r[2], "city": r[3], "pcp": r[4]} for r in rows}

    print("\n=== PRECISION: held-out attribute agreement ===")
    print(f"{'match_method':<16}{'n':>9}{'address':>10}{'city':>8}{'pcp':>8}")
    for m in ("exact", "exact_tiebreak", "fuzzy", "random_control"):
        if m in by:
            d = by[m]
            print(f"{m:<16}{d['n']:>9,}{d['addr']:>9.1f}%{d['city']:>7.1f}%{d['pcp']:>7.1f}%")

    ceiling, floor, fuzzy = by["exact"], by["random_control"], by["fuzzy"]
    print("\nestimated precision of fuzzy links "
          "(observed - random) / (exact - random):")
    ests = {}
    for sig in ("addr", "city", "pcp"):
        est = (fuzzy[sig] - floor[sig]) / (ceiling[sig] - floor[sig])
        ests[sig] = est
        print(f"  via {sig:<8} {est * 100:.1f}%")
    mean = sum(ests.values()) / len(ests)
    bad = fuzzy["n"] * (1 - mean)
    total = sum(by[m]["n"] for m in ("exact", "exact_tiebreak", "fuzzy"))
    print(f"\n  fuzzy precision      ~{mean * 100:.1f}%  (3 signals agree within "
          f"{(max(ests.values()) - min(ests.values())) * 100:.1f}pp)")
    print(f"  est. wrong links     ~{bad:,.0f} of {fuzzy['n']:,} fuzzy")
    print(f"  crosswalk precision  ~{100 * (total - bad) / total:.2f}% "
          f"over all {total:,} links")
    return {"fuzzy_precision": mean, "est_wrong": bad, "total": total, "by": by}


def measure_recall(con, sample: int) -> dict:
    print(f"\n=== RECALL: held-out corruption (n={sample:,} per type) ===")
    con.execute(
        f"""CREATE OR REPLACE TABLE truth AS
            SELECT p.patient_id, p.first_name, p.last_name, p.dob, p.gender, p.zip,
                   x.member_id AS true_member_id
            FROM marts.identity_xwalk x
            JOIN raw.ehr_patients p USING (patient_id)
            WHERE x.match_method = 'exact'
            ORDER BY hash(p.patient_id) LIMIT {sample}"""
    )
    print(f"{'corruption':<24}{'matched':>9}{'correct':>9}{'recall':>9}{'wrong':>8}")
    results = {}
    for name, expr in CORRUPTIONS.items():
        con.execute(
            f"CREATE OR REPLACE TABLE perturbed AS SELECT patient_id, {expr} FROM truth"
        )
        con.execute(retarget_matcher("perturbed", "recall_result"))
        matched, correct = con.execute(
            """SELECT count(*),
                      count(*) FILTER (WHERE r.member_id = t.true_member_id)
               FROM truth t LEFT JOIN recall_result r USING (patient_id)
               WHERE r.member_id IS NOT NULL"""
        ).fetchone()
        n = con.execute("SELECT count(*) FROM truth").fetchone()[0]
        recall = correct / n
        results[name] = {"matched": matched, "correct": correct,
                         "recall": recall, "wrong": matched - correct}
        print(f"{name:<24}{matched:>9,}{correct:>9,}{recall * 100:>8.1f}%"
              f"{matched - correct:>8,}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=3000, help="patients per corruption")
    ap.add_argument("--skip-recall", action="store_true")
    args = ap.parse_args()

    if not DB.exists():
        raise SystemExit(f"{DB} not found — run `make marts`")

    # Work on a copy: the matcher issues CREATE OR REPLACE TABLE, and the real
    # warehouse must never be mutated by a measurement.
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "scratch.duckdb"
        shutil.copy(DB, scratch)
        con = duckdb.connect(str(scratch))
        try:
            measure_precision(con)
            if not args.skip_recall:
                measure_recall(con, args.sample)
        finally:
            con.close()
    print("\n(measured on a scratch copy; data/warehouse.duckdb untouched)")


if __name__ == "__main__":
    main()

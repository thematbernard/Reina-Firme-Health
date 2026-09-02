"""Measure the query path instead of calling it fast.

The brief's third complaint is "no fast query path". "Fast" is an adjective
until something is timed, so this times the same strategy questions three ways:

  mart    — marts.* in DuckDB              (what we built)
  raw     — hand-assembled joins in DuckDB  (what the shape was before marts)
  redshift— the same hand-assembled SQL against source (the actual baseline)

Redshift is skipped automatically if unreachable; the run still reports the
mart-vs-raw comparison, which is the shape improvement.

Cold vs warm matters: DuckDB reads parquet, so first touch pays I/O. Both are
reported — quoting only warm numbers would flatter the result.

Run:  make benchmark
"""

import argparse
import json
import os
import statistics
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "warehouse.duckdb"

# Each question, expressed against the marts and against raw. The raw variants
# are the real pre-mart SQL, lifted from analysis/sacramento_vs_atlanta.sql.
QUESTIONS = {
    "q2_clinic_comparison": {
        "mart": """
            SELECT city, avg(appts_completed)
            FROM marts.facility_metrics
            WHERE ownership = 'owned' AND facility_type = 'clinic'
              AND city IN ('Sacramento', 'Atlanta')
            GROUP BY 1""",
        "raw": """
            SELECT f.city, count(*) FILTER (WHERE a.status = 'completed') * 1.0
                   / count(DISTINCT f.facility_id)
            FROM raw.ops_appointments a
            JOIN raw.ops_facilities f USING (facility_id)
            WHERE f.ownership = 'owned' AND f.facility_type = 'clinic'
              AND f.city IN ('Sacramento', 'Atlanta')
              AND a.scheduled_dt_local >= DATE '2025-06-01'
              AND a.scheduled_dt_local <  DATE '2026-06-01'
            GROUP BY 1""",
    },
    "q1_market_ranking": {
        "mart": """
            SELECT city, members_active, owned_hospitals, median_miles_to_acute,
                   recapture_plan_paid_musd
            FROM marts.market_summary
            WHERE members_active > 20000
            ORDER BY median_miles_to_acute DESC LIMIT 10""",
        "raw": """
            WITH mem AS (
                SELECT member_id, city, latitude lat, longitude lon
                FROM raw.payer_members
                WHERE termination_date IS NULL OR termination_date > current_date),
            cl AS (
                SELECT m.city,
                       3959 * 2 * asin(sqrt(
                           pow(sin(radians(f.latitude - m.lat) / 2), 2)
                         + cos(radians(m.lat)) * cos(radians(f.latitude))
                           * pow(sin(radians(f.longitude - m.lon) / 2), 2))) miles
                FROM raw.payer_claims c
                JOIN mem m USING (member_id)
                JOIN raw.ops_facilities f ON f.facility_id = c.facility_id
                WHERE c.service_date >= DATE '2025-06-01'
                  AND c.service_date <  DATE '2026-06-01'
                  AND c.service_line IN ('surgery','cardiology','er','oncology')),
            mkt AS (
                SELECT city, count(*) n, median(miles) med FROM cl GROUP BY 1)
            SELECT k.city, count(m.member_id) members, med
            FROM mkt k JOIN raw.payer_members m ON m.city = k.city
            WHERE k.n > 20000 GROUP BY 1, 3 ORDER BY 3 DESC LIMIT 10""",
    },
    "leakage_by_market": {
        "mart": """
            SELECT city, pct_acute_in_market, nonowned_acute_plan_paid_musd
            FROM marts.market_summary WHERE members_active > 20000
            ORDER BY pct_acute_in_market""",
        "raw": """
            WITH mm AS (SELECT member_id, city FROM raw.payer_members)
            SELECT mm.city,
                   100.0 * count(*) FILTER (WHERE f.city = mm.city) / count(*),
                   sum(c.plan_paid) FILTER (WHERE f.ownership <> 'owned') / 1e6
            FROM raw.payer_claims c
            JOIN mm USING (member_id)
            JOIN raw.ops_facilities f ON f.facility_id = c.facility_id
            WHERE c.service_date >= DATE '2025-06-01'
              AND c.service_date <  DATE '2026-06-01'
              AND c.service_line IN ('surgery','cardiology','er','oncology')
            GROUP BY 1 HAVING count(*) > 20000 ORDER BY 2""",
    },
}

# Redshift dialect differs from DuckDB in ways that matter here, so the source
# queries are written out explicitly rather than machine-translated:
#   - no `count(*) FILTER (WHERE ...)`  -> sum(CASE WHEN ... THEN 1 ELSE 0 END)
#   - `pow()` is `POWER()`
#   - schema names are payer.claims, not raw.payer_claims
REDSHIFT_SQL = {
    "q2_clinic_comparison": """
        SELECT f.city, SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END) * 1.0
               / COUNT(DISTINCT f.facility_id)
        FROM ops.appointments a
        JOIN ops.facilities f ON f.facility_id = a.facility_id
        WHERE f.ownership = 'owned' AND f.facility_type = 'clinic'
          AND f.city IN ('Sacramento', 'Atlanta')
          AND a.scheduled_dt_local >= DATE '2025-06-01'
          AND a.scheduled_dt_local <  DATE '2026-06-01'
        GROUP BY 1""",
    "q1_market_ranking": """
        WITH mem AS (
            SELECT member_id, city, latitude AS lat, longitude AS lon
            FROM payer.members
            WHERE termination_date IS NULL OR termination_date > CURRENT_DATE),
        cl AS (
            SELECT m.city,
                   3959 * 2 * ASIN(SQRT(
                       POWER(SIN(RADIANS(f.latitude - m.lat) / 2), 2)
                     + COS(RADIANS(m.lat)) * COS(RADIANS(f.latitude))
                       * POWER(SIN(RADIANS(f.longitude - m.lon) / 2), 2))) AS miles
            FROM payer.claims c
            JOIN mem m ON m.member_id = c.member_id
            JOIN ops.facilities f ON f.facility_id = c.facility_id
            WHERE c.service_date >= DATE '2025-06-01'
              AND c.service_date <  DATE '2026-06-01'
              AND c.service_line IN ('surgery', 'cardiology', 'er', 'oncology'))
        SELECT city, COUNT(*) AS n, MEDIAN(miles) AS med
        FROM cl GROUP BY 1 HAVING COUNT(*) > 20000 ORDER BY 3 DESC LIMIT 10""",
    "leakage_by_market": """
        SELECT m.city,
               100.0 * SUM(CASE WHEN f.city = m.city THEN 1 ELSE 0 END) / COUNT(*),
               SUM(CASE WHEN f.ownership <> 'owned' THEN c.plan_paid ELSE 0 END) / 1e6
        FROM payer.claims c
        JOIN payer.members m ON m.member_id = c.member_id
        JOIN ops.facilities f ON f.facility_id = c.facility_id
        WHERE c.service_date >= DATE '2025-06-01'
          AND c.service_date <  DATE '2026-06-01'
          AND c.service_line IN ('surgery', 'cardiology', 'er', 'oncology')
        GROUP BY 1 HAVING COUNT(*) > 20000 ORDER BY 2""",
}


def time_it(fn, reps: int) -> dict:
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return {"cold_s": times[0], "warm_s": statistics.median(times[1:]) if reps > 1 else times[0],
            "all": times}


def bench_duckdb(reps: int) -> dict:
    out = {}
    for name, variants in QUESTIONS.items():
        out[name] = {}
        for shape in ("mart", "raw"):
            # fresh connection per shape so the cold number is honestly cold
            con = duckdb.connect(str(DB), read_only=True)
            sql = variants[shape]
            try:
                r = time_it(lambda: con.execute(sql).fetchall(), reps)
                out[name][shape] = r
            finally:
                con.close()
    return out


def bench_redshift(reps: int) -> dict | None:
    try:
        import redshift_connector
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        conn = redshift_connector.connect(
            host=os.environ["host"].strip(), port=int(os.environ["port"].strip()),
            database=os.environ["database"].strip(), user=os.environ["username"].strip(),
            password=os.environ["password"].strip(), ssl=True, timeout=120,
        )
    except Exception as e:
        print(f"\nRedshift baseline NOT MEASURED — {type(e).__name__}: {str(e)[:90]}")
        print("  A connection timeout means the source is unreachable from here")
        print("  (the assessment requires the client IP to be whitelisted; that")
        print("   access has lapsed). Re-whitelist and rerun `make benchmark` to")
        print("   fill in the baseline column. It is reported as '—', never estimated.")
        return None
    # Redshift caches query results by default, which would report ~40ms for a
    # scan of millions of rows and make the baseline meaningless. Turn it off so
    # every rep does real work.
    try:
        c0 = conn.cursor()
        c0.execute("SET enable_result_cache_for_session TO off")
        conn.commit()
        print("  (result cache disabled for this session)")
    except Exception as e:
        print(f"  WARNING could not disable result cache: {type(e).__name__} — "
              "warm numbers may be cache hits, treat them as a floor")

    out = {}
    for name in QUESTIONS:
        sql = REDSHIFT_SQL[name]
        try:
            cur = conn.cursor()
            out[name] = time_it(lambda: (cur.execute(sql), cur.fetchall()), reps)
            print(f"  redshift {name}: {out[name]['warm_s']:.2f}s warm, "
                  f"{out[name]['cold_s']:.2f}s cold")
        except Exception as e:
            print(f"  redshift {name}: FAILED {type(e).__name__}: {str(e)[:110]}")
            out[name] = None
            try:
                conn.rollback()   # Redshift aborts the txn on error
            except Exception:
                pass
    conn.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--skip-redshift", action="store_true")
    ap.add_argument("--out", default=str(Path(__file__).parent / "benchmark.json"))
    args = ap.parse_args()

    if not DB.exists():
        raise SystemExit(f"{DB} not found — run `make marts`")

    print(f"query path benchmark — {args.reps} reps per query\n")
    duck = bench_duckdb(args.reps)
    red = None if args.skip_redshift else bench_redshift(args.reps)

    print(f"\n{'question':<24}{'mart':>9}{'duck raw':>10}{'redshift':>11}"
          f"{'vs raw':>9}{'vs rshift':>11}")
    for name in QUESTIONS:
        m, r = duck[name]["mart"], duck[name]["raw"]
        rs = red.get(name) if red else None
        rs_txt = f"{rs['warm_s']:>9.2f}s" if rs else "        —"
        vs_rs = f"{rs['warm_s'] / m['warm_s']:>9.0f}x" if rs else "        —"
        print(f"{name:<24}{m['warm_s'] * 1000:>7.1f}ms{r['warm_s'] * 1000:>8.1f}ms"
              f"{rs_txt}{r['warm_s'] / m['warm_s']:>8.0f}x{vs_rs}")
    print("  (all warm/median-of-reps; mart cold "
          f"{max(duck[q]['mart']['cold_s'] for q in QUESTIONS) * 1000:.1f}ms, "
          f"duck raw cold "
          f"{max(duck[q]['raw']['cold_s'] for q in QUESTIONS) * 1000:.0f}ms)")

    marts_total = sum(duck[q]["mart"]["warm_s"] for q in QUESTIONS)
    raw_total = sum(duck[q]["raw"]["warm_s"] for q in QUESTIONS)
    print(f"\nall {len(QUESTIONS)} questions: mart {marts_total * 1000:.0f}ms "
          f"vs raw {raw_total * 1000:.0f}ms ({raw_total / marts_total:.1f}x)")
    if red:
        got = [red[q] for q in QUESTIONS if red.get(q)]
        if got:
            rt = sum(g["warm_s"] for g in got)
            print(f"redshift ({len(got)}/{len(QUESTIONS)} completed): {rt:.1f}s "
                  f"-> {rt / marts_total:.0f}x slower than marts")

    Path(args.out).write_text(json.dumps(
        {"reps": args.reps, "duckdb": duck, "redshift": red}, indent=2, default=str))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

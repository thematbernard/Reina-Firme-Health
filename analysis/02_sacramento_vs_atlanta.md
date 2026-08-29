# Why is utilization at our Sacramento clinic 40% below our Atlanta clinic of similar size?

**Answer: it isn't.** The premise does not hold in this data. Matched on size,
the Sacramento and Atlanta clinics differ by **0.4%**, and the widest gap
between *any two* of the 64 owned clinics is **2.9%**. A 40% gap is not
findable here because it is not arithmetically constructible from clinic
throughput.

There *is* a real and actionable Sacramento problem, but it is a **network
composition** problem, not a utilization problem — see §4.

Reproduce every number: `analysis/sacramento_vs_atlanta.sql` (`make analysis`).

---

## 1. A 40% gap is not possible on throughput

Completed appointments per owned clinic, all 64 clinics, ops window
2025-06 → 2026-05:

| n | min | max | mean | sd | CV | max/min |
|---|---|---|---|---|---|---|
| 64 | 17,798 | 18,309 | 18,038 | 122 | **0.68%** | **1.029** |

The p10–p90 range is 17,865–18,191. To produce a 40% gap you need
max/min ≈ 1.67; the observed maximum across the entire network is 1.029.

Confirmed against an **independent volume source** — EHR encounters, a
different table with a different grain — which gives CV 1.27% and max/min
1.068. Two unrelated sources agreeing on near-uniformity is not a
coincidence of one bad extract.

The same flatness holds for the hospital metrics: OR utilization spans
51.7-54.6% across the 8 owned hospitals (max/min 1.056) and bed occupancy
54.1-55.4% (max/min 1.024). Note the OR denominator: distinct `or_room` x
*actual* operating days (~270-290/yr) x 10h. Using 365 days understates every
facility to 40.4-41.5% without changing the spread.

## 2. The size-matched pair differs by 0.4%

"Similar size" made precise: the Sacramento and Atlanta clinics whose
attributed panels are closest (within 0.1%).

| | Sacramento FAC-00015 | Atlanta FAC-00052 | gap |
|---|---|---|---|
| attributed panel | 11,190 | 11,174 | 0.1% |
| completed appointments | 18,244 | 18,309 | **0.4%** |
| scheduled appointments | 42,219 | 42,357 | 0.3% |
| EHR encounters | 34,636 | 36,934 | 6.2% |
| no-show rate | 14.1% | 14.0% | 0.1pp |
| per panel member | 1.630 | 1.639 | 0.5% |

Every operational metric matches. No-show and cancellation behaviour is
identical, so the gap is not hiding in demand realization either.

## 3. Any "gap" you find is a denominator artifact — and it points the other way

Because the numerator is effectively constant (CV 0.68%), any utilization
ratio is really just `18,000 / denominator`. The choice of denominator
manufactures the answer:

| Denominator | Sacramento | Atlanta | Sacramento vs Atlanta |
|---|---|---|---|
| per clinic | 18,040 | 18,105 | −0.4% |
| per provider based there | 278.6 | 251.9 | **+10.6%** |
| per attributed panel member | 1.951 | 1.525 | **+27.9%** |
| per market member | 1.308 | 1.084 | **+20.7%** |

**Three of four denominators put Sacramento *above* Atlanta**, and the fourth
is a rounding difference. None yields −40%.

This is the trap. Panel-normalized utilization has a genuine 3.18x spread
across the network (0.93 → 2.96), which looks like a rich signal — but it is
entirely denominator variance, since the numerator barely moves. An analyst
who reached for it would "explain" a 52% gap between Atlanta FAC-00040 (1.135,
3rd lowest in the network) and Sacramento FAC-00030 (2.396) — a gap with the
sign reversed from the premise and no operational meaning at all.

Sacramento's four clinics rank **above the Atlanta median** on every
normalized measure.

## 4. What the Sacramento data does show

A structural network gap, visible in facility composition:

| Market | Members | Clinics | Hospitals | Urgent care |
|---|---|---|---|---|
| Sacramento | 55,183 | 4 | **0** | **0** |
| Atlanta | 133,598 | 8 | 1 | 2 |

Sacramento is the largest owned-clinic market with **no owned hospital and no
owned urgent care**. The nearest owned hospitals are Fremont, San Francisco
and San Jose — all outside the market.

Consequence: Sacramento exports its expensive care. Share of member allowed
dollars spent at facilities **outside the member's own market**, 3-year claims
window:

| Market | Total allowed | Out of market | % out | Per year |
|---|---|---|---|---|
| Sacramento | $825.3M | **$684.4M** | **82.9%** | $228.1M |
| Atlanta | $1,980.8M | $613.3M | 31.0% | $204.4M |

The mechanism is specifically **hospital care**, exactly as the missing-asset
thesis predicts:

| Sacramento members' claims | Claims | Allowed | Avg/claim |
|---|---|---|---|
| hospital, **out of market** | 292,498 | **$657.2M** | $2,247 |
| clinic, in market | 433,148 | $110.5M | $255 |
| hospital, in market (partner only) | 22,772 | $30.4M | $1,335 |

**92.8% of Sacramento's hospital claims leave the market**, carrying 79.6% of
the market's entire allowed spend. Atlanta, which has an owned hospital,
retains 67.9% of its hospital dollars in market. Sacramento's displaced volume
lands in San Francisco (88,211 owned + 46,485 partner claims), San Jose partner
(50,848) and Stockton partner (35,030).

Note this is invisible in the per-member averages, which are near-identical
(16.2 claims/member in both markets; $15,527 vs $15,406 allowed per member;
37.9% vs 38.2% of dollars at partner facilities). Sacramento does not spend
more — it spends it somewhere else, at facilities Reina Firme does not own.

## 5. What we recommend saying

1. The 40% figure does not reconcile to any metric in the warehouse. Ask the
   Strategy team for its provenance and denominator — it is most likely a
   panel- or capacity-normalized ratio from a source system we don't have, or
   a comparison of unlike facility types.
2. Do not build a utilization improvement plan for the Sacramento clinics.
   They are performing at or above the Atlanta clinics on every measure we can
   construct.
3. The real Sacramento question is **acute-care access**, and it feeds the
   "where do we open next" question directly: 55,183 members, zero owned
   hospital or urgent care, and **$228M/year of allowed spend leaving the
   market** — $219M/year of it hospital care. That is the business case to
   evaluate, and it is a far larger number than any utilization fix could
   recover.

## 6. Caveats on this conclusion

- **The near-uniformity is itself suspicious** and most likely an artifact of
  how this dataset was generated: per-facility volume looks drawn from a tight
  distribution around a common mean. In production data, clinic throughput
  varies far more than 0.68%. The honest statement is that *this warehouse*
  cannot support the premise — not that Reina Firme's real clinics are
  identical.
- Recorded as caveat **C1** in `semantic/dictionary.md`:
  `ops_appointments.provider_id` is randomly assigned (1.2% agreement with the
  provider's own facility, i.e. chance across 84 sites), so it cannot be used
  as a capacity denominator. Staffing comes from
  `ops_providers.primary_facility_id`.
- Ops tables cover 2025-06 → 2026-05 only; claims cover three years. All
  comparisons above are windowed consistently (dictionary rule R2).
- Facility counts filter `ownership='owned'`; `ops_facilities` holds all 284
  facilities including partners (caveat C5).

# Where should we open the next facility, and what services should it offer?

**Open in Sacramento, as an acute-care hospital — not another clinic.**

Sacramento is the largest market in the network with **zero owned hospitals and
zero owned urgent cares**, and its members travel further for acute care than
anyone else by a wide margin. The ambulatory need is already met by the four
owned clinics there; the gap is hospital-based care.

Every number below is one query against `marts.market_summary`,
`marts.market_flows` or `marts.facility_metrics`. Reproduce with `make analysis`,
which runs
[`01_next_facility.sql`](01_next_facility.sql) — its blocks are in the section
order used here.

## 1. Sacramento is the access outlier

Acute care = `service_line in (surgery, cardiology, er, oncology)`. Trailing 12
months, straight-line miles from member home to the facility that served them.

| Market | Active members | Owned hosp | Owned UC | Owned clinics | % acute in-market | Median miles | % over 30mi |
|---|---|---|---|---|---|---|---|
| **Sacramento** | **50,618** | **0** | **0** | 4 | **4.2%** | **75.5** | **95.7%** |
| Modesto | 21,137 | 0 | 1 | 0 | 2.6% | 53.2 | 93.9% |
| Stockton | 30,785 | 0 | 1 | 4 | 5.1% | 48.9 | 93.1% |
| Oakland | ~42,400 | 0 | 0 | 2 | 3.3% | 12.6 | 29.7% |
| Atlanta | 122,480 | 1 | 2 | 8 | 68.5% | 9.1 | 6.2% |

Sacramento's median is **8x Atlanta's**, and 95.7% of its acute claims are served
more than 30 miles from home.

## 2. Why Sacramento and not Oakland — travel distance decides it

Oakland also has zero owned hospitals, so member count alone would not separate
them. What separates them is **fallback distance**: Oakland sits 12.6 median
miles from owned hospitals in San Francisco and Fremont. Sacramento has no such
fallback — the nearest owned hospitals are San Francisco, Fremont and San Jose,
all outside the market.

That single column is the decision. It is also why market ranking must use
geographic measures rather than ownership share: **owned dollar share is
61–63% in every city** and carries no cross-market signal at all (caveat C6).

**Leakage share does not separate them either, and points the wrong way.**
Oakland sends **94.3%** of its allowed dollars out of market against
Sacramento's 82.8% — because out-of-market and out-of-network are different
things. Most of both cities' out-of-market spend lands at *owned* facilities
(Oakland 59.2%, Sacramento 48.8% of all allowed). Oakland's leaves the city and
travels 12.6 miles; Sacramento's leaves and travels 75.5. Distance is the
measure that separates the two markets, which is why the recommendation rests
on it.

## 3. Sacramento anchors a three-market region — but not one catchment

Stockton (48.9 median miles to acute care) and Modesto (53.2) have the same
structural problem and no owned hospital either. As a region:

- **102,540 active members**
- **$33.2M/yr** recoverable plan-paid spend (Sacramento $16.5M, Stockton $10.0M,
  Modesto $6.7M)

**That is a regional opportunity, not a single building's business case, and the
distinction is load-bearing.** Measured from the Sacramento owned-clinic
centroid to active member homes:

| market | members | median miles | within 30mi | within 45mi |
|---|---|---|---|---|
| Sacramento | 50,639 | 3.8 | 100% | 100% |
| Stockton | 30,799 | 46.1 | 0.2% | **32.3%** |
| Modesto | 21,148 | 71.9 | 0% | **0%** |

Modesto's members sit **71.9 miles** from a Sacramento site — essentially the
same 75.5-mile trip this analysis calls unacceptable. By its own standard, a
Sacramento hospital does not serve Modesto. A realistic catchment is Sacramento
plus the ~32% of Stockton inside 45 miles: **~60,500 active members**, and
**~$19.7M/yr** of the $33.2M.

Stockton is the phase-2 site, on its own merits (30,799 members, 48.9 median
miles, 93.1% over 30). Modesto is a third decision, not a spillover.

## 4. What services — only the hospital lines are leaking

Corridor members, trailing 12 months, from `marts.market_flows` — **one table,
no joins**. "Served in corridor" means the facility that handled the claim sits
in Sacramento, Stockton or Modesto, whoever owns it; this is an access measure,
not a market-share measure. The split is unusually clean:

| Service line | Allowed | % served in corridor |
|---|---|---|
| **surgery** | **$221.5M** | **11.7%** |
| **cardiology** | **$113.5M** | **11.7%** |
| **er** | **$58.1M** | **11.9%** |
| oncology | $0.9M | 11.4% |
| imaging | $60.0M | 73.1% |
| primary_care | $38.3M | 71.8% |
| labs | $4.2M | 72.8% |
| behavioral | $2.6M | 73.1% |

Ranked by *recoverable plan-paid* rather than gross spend (rule R6), the order
is the same and the case is sharper: **surgery $18.7M/yr, cardiology $9.6M,
ER $4.8M** — against imaging $5.0M and primary care $3.2M, which would be
recaptured by clinics that already exist.

**Build for surgery, cardiology and an ED. Do not build more ambulatory
capacity** — imaging, primary care, labs and behavioral are already ~72%
retained by the existing clinics, so adding more captures little. Oncology is
genuinely small here ($0.9M corridor-wide); do not build for it.

The ED matters beyond its $58.1M: unplanned volume cannot travel 75 miles, so it
is the only line where distance is a clinical risk rather than an inconvenience.

## 5. Sizing and the financial case

**~110 beds, 6–8 ORs**, for a catchment of ~60,500 active members (Sacramento
plus the reachable third of Stockton). Three independent anchors agree:

| basis | beds | ORs |
|---|---|---|
| network capacity per active member (2,147 beds, 114 ORs, 1,008,234 members) | 129 | 6.8 |
| Atlanta FAC-00006's own ratio (206 beds, 12 ORs, 122,480 members) | 102 | 5.9 |
| Sacramento-only, network ratio (50,639 members) | 108 | 5.7 |

**An earlier draft of this analysis said ~200 beds and 12–14 ORs.** That took
Atlanta's absolute hospital size as the template without scaling for a market
41% its size, and it implicitly assumed the whole corridor was one catchment —
which §3 shows it is not. The corrected figure is roughly half.

Note that observed utilization cannot validate a capacity plan in this dataset:
all eight owned hospitals run 54.1–55.4% bed occupancy regardless of size, the
441-bed and 206-bed hospitals within 0.7pp of each other (caveat C6 again). The
per-member ratios are the only defensible anchor.

**Do not "just redirect volume to existing capacity."** All eight owned hospitals
have headroom — OR utilization 51.7–54.6%, bed occupancy 54.1–55.4% — but the
nearest is 75 miles away. That headroom is unreachable for Sacramento members and
irrelevant for an ED.

**The saving is in `plan_paid`, not `allowed_amount`.** Average allowed is
essentially identical regardless of where care happens (~$951 owned, ~$957
partner, ~$955 out-of-network), so a business case built on allowed dollars shows
no benefit at all. What differs is the share Reina Firme pays:

| network status | plan_paid / allowed |
|---|---|
| owned | **0.44** |
| in-network partner | 0.624 |
| out-of-network | 0.80 |

Repricing the corridor's non-owned acute volume at the owned ratio gives
**$33.2M/yr**. Separately, the ~$97M/yr of allowed spend currently served at San
Francisco owned hospitals would be served locally — no unit-cost saving, but it
frees SF/Fremont OR and bed capacity and removes an 85-mile access barrier.

## 6. Honest caveats

- **Recapture dollars alone would pick Atlanta, not Sacramento.** Atlanta's
  recoverable figure is $39.5M/yr against Sacramento's $16.5M, simply because
  big markets leak more in absolute terms — and Atlanta already *has* the asset,
  so that leakage is far harder to recapture. **The case for Sacramento rests on
  access, not on absolute dollars**, and only becomes the dollar winner as a
  corridor. A test (`test_recapture_dollars_do_not_by_themselves_pick_sacramento`)
  pins this so the narrative cannot quietly drift.
- **$33.2M assumes full recapture** at current owned cost ratios. A realistic
  ramp is lower. Treat it as the ceiling on the operating case, not a forecast.
- **Distances are straight-line, not drive time.**
  `raw.external_drive_time_isochrones` holds 252 precomputed polygons and is
  unused. This almost certainly *understates* Sacramento's disadvantage, so it
  strengthens the recommendation — but it should be measured.
- **This conclusion is not an artefact of the semantic layer.** An earlier
  caveat C2b stated it outright in `semantic/dictionary.md`, which the agent
  reads before writing any SQL. C2b is gone; with every market-naming caveat
  stripped, 3 of 3 fresh agent runs still reach Sacramento and acute care on
  an access measure (`make ablation`, `evals/ablation.json`). Note those runs
  treated the corridor as one catchment — the §3 correction is not something
  the dictionary supplies.
- **No capital cost, staffing, licensure or CON analysis here.** This sizes the
  demand-side opportunity only.
- **Demographics do not differentiate markets** in this data (average age
  42.1–42.4, 10.4–10.7% aged 65+ everywhere), so case-mix arguments are not
  available. Network footprint and geography are the only real variation.

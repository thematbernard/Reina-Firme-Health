# Where should we open the next facility, and what services should it offer?

**Open in Sacramento, as an acute-care hospital — not another clinic.**

Sacramento is the largest market in the network with **zero owned hospitals and
zero owned urgent cares**, and its members travel further for acute care than
anyone else by a wide margin. The ambulatory need is already met by the four
owned clinics there; the gap is hospital-based care.

Every number below is one query against `marts.market_summary` or
`marts.facility_metrics`. Reproduce with `make analysis`.

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

## 3. Sacramento anchors a three-city corridor

Stockton (48.9 median miles) and Modesto (53.2) have the same problem and no
owned hospital either. Together:

- **102,540 active members** — comparable to Atlanta's 122,480, which supports
  one 206-bed owned hospital
- **$33.2M/yr** recoverable plan-paid spend (Sacramento $16.5M, Stockton $10.0M,
  Modesto $6.7M)

## 4. What services — only the hospital lines are leaking

Corridor members, trailing 12 months. The split is unusually clean:

| Service line | Allowed | % served in corridor |
|---|---|---|
| **surgery** | **$221.5M** | **11.8%** |
| **cardiology** | **$113.5M** | **11.6%** |
| **er** | **$58.1M** | **11.8%** |
| oncology | $0.9M | 10.9% |
| imaging | $60.0M | 73.1% |
| primary_care | $38.3M | 71.8% |
| labs | $4.2M | 72.8% |
| behavioral | $2.6M | 73.1% |

**Build for surgery, cardiology and an ED. Do not build more ambulatory
capacity** — imaging, primary care, labs and behavioral are already ~72%
retained by the existing clinics, so adding more captures little. Oncology is
genuinely small here ($0.9M corridor-wide); do not build for it.

The ED matters beyond its $58.1M: unplanned volume cannot travel 75 miles, so it
is the only line where distance is a clinical risk rather than an inconvenience.

## 5. Sizing and the financial case

**~200 beds, 12–14 ORs**, benchmarked on Atlanta's owned hospital (FAC-00006:
206 beds, 12 ORs, serving 122,480 active members at 53.3% OR utilization and
54.7% bed occupancy).

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
- **No capital cost, staffing, licensure or CON analysis here.** This sizes the
  demand-side opportunity only.
- **Demographics do not differentiate markets** in this data (average age
  42.1–42.4, 10.4–10.7% aged 65+ everywhere), so case-mix arguments are not
  available. Network footprint and geography are the only real variation.

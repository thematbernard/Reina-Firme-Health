# Vi Applied AI Assessment — Build Plan

**Problem chosen:** #3 — "The Strategy team can't get answers fast enough" (Reina Firme Health)

**Thesis:** Unify Reina Firme's fragmented data into a small set of clean analytical marts, put an
LLM-queryable MCP server on top with a semantic layer, and use it to concretely answer the two
strategy questions (next clinic location + Sacramento underperformance). Deliver *insight* and the
*repeatable capability* that produced it.

**Time budget:** ~8–10 hours of real work across the 7-day window. Timebox each phase; cut scope
from the bottom of each phase, never from the demo path.

---

## 1. Build flow (phased, in order)

### Phase 0 — Setup & access (~30 min, do before window opens)
- [ ] Send public IP to Vi contact for whitelisting: `curl https://checkip.amazonaws.com`
- [ ] Create GitHub repo (see §3) with README skeleton, `.gitignore`, `.env.example`
- [ ] Read the dataset specification end-to-end; note ambiguities → send 1–2 sharp questions
      to the Vi contact early (they explicitly grade on this)
- [ ] Verify connectivity once credentials arrive: `psql` smoke test, list schemas/tables

### Phase 1 — Explore & profile the data (~1.5 hr)
- [ ] Row counts, date ranges, null rates per table; keys and join paths
- [ ] Confirm/deny the stated fragmentation: is there a unified member ID? facility ID overlap
      between claims, utilization, and network tables?
- [ ] Write findings into `docs/data-notes.md` as you go — this becomes the assumptions
      section of the write-up for free

### Phase 2 — Light data engineering: identity + marts (~2 hr)
Since access is read-only Redshift, build marts locally in **DuckDB** (extract via SQL → parquet).
- [ ] Entity resolution where needed (member identity across systems, facility name/ID mapping)
- [ ] 3–4 analytical marts, e.g.:
      - `mart_member` — one row per member: demographics, plan, geography, program enrollments
      - `mart_encounters` — claims/visits with resolved facility, owned/partner/OON flag, cost
      - `mart_facility_utilization` — capacity vs. actual by facility/service line/month
      - `mart_market` — geo rollups: members, utilization, leakage, drive-time coverage by area
- [ ] Everything reproducible: numbered SQL/Python scripts in `pipeline/`, one `make build` entry point

### Phase 3 — Semantic layer + MCP server (~2.5 hr) ← the differentiator
- [ ] `semantic/` — YAML/Markdown data dictionary the agent reads: table purposes, column
      definitions, metric formulas (e.g. "leakage rate =", "utilization ="), known join paths, caveats
- [ ] MCP server (Python, official `mcp` SDK) exposing tools:
      - `list_tables` / `describe_table` — schema + semantic-layer context, not raw DDL
      - `run_query` — read-only SQL against the DuckDB marts, row-limited, with guardrails
      - `get_metric_definitions` — canonical metric formulas so the agent doesn't invent them
      - (stretch) `compare_facilities`, `market_summary` — curated high-level tools
- [ ] Wire into Claude Desktop / Claude Code for the live demo
- [ ] Small **eval set**: 8–10 questions with known answers (computed directly in Phase 2);
      script that runs them through the agent and checks results. This is the trust story.

### Phase 4 — Answer the two strategy questions (~1.5 hr)
Use your own tool (dogfooding is part of the demo narrative), verify by hand:
- [ ] **Next clinic:** rank candidate geographies by member density, current leakage spend,
      drive-time gaps, service-line demand → recommendation with a map/chart
- [ ] **Sacramento vs. Atlanta:** decompose the 40% gap — panel size, service mix, referral
      patterns, staffing/capacity, member demographics → ranked hypotheses with evidence
- [ ] Save both as short analysis notebooks/markdown in `analysis/` with charts

### Phase 5 — Deliverables packaging (~2 hr)
- [ ] **Write-up** (README or `docs/writeup.md`, 1–3 pages): architecture diagram, key decisions
      & tradeoffs, assumptions, tools used (incl. LLMs/code assistants — they ask), "next week" roadmap
- [ ] **Exec deck** (5–8 slides): problem framing → the two answered questions (lead with insight)
      → how the tool works (1 slide) → business impact → risks (data quality, hallucinated SQL,
      governance) → what's next
- [ ] **Demo prep:** scripted happy path + one unscripted-feeling question; record a fallback
      walkthrough video in case live demo breaks
- [ ] Log actual hours spent (they ask for it)

---

## 2. Tool choices

| Layer | Tool | Why |
|---|---|---|
| Warehouse access | `psql` + Python (`redshift-connector` or `psycopg2`) | Read-only Redshift; simple, no infra |
| Local analytics store | **DuckDB** (+ parquet extracts) | Fast, zero-setup, keeps marts reproducible without write access to Redshift |
| Pipeline | Plain Python + SQL scripts, `Makefile` | dbt is overkill for 10 hours; numbered scripts are reviewable |
| Data work | pandas / DuckDB SQL, Jupyter for exploration | Standard, fast |
| MCP server | Python **`mcp` SDK** (official) | The centerpiece; official SDK, demo via Claude Desktop/Claude Code |
| LLM | Claude (Sonnet/Opus via Claude Desktop or API) | What Vi would expect; MCP-native |
| Charts | matplotlib or plotly, exported to the deck | Keep it simple |
| Deck | Google Slides or Keynote | Don't engineer this |
| Env/secrets | `.env` + `python-dotenv`; `uv` for deps | Credentials never committed |

Disclose in the write-up: Claude Code used for development (they explicitly encourage it).

---

## 3. Repo setup & sharing with Vi

### Create
```bash
mkdir -p ~/Projects/vi-assessment && cd ~/Projects/vi-assessment
git init
gh repo create reina-firme-strategy-engine --private --source=. --push
```
Start **private**; flip to public (or add collaborators) when submitting — don't develop in public.

### Structure
```
reina-firme-strategy-engine/
├── README.md              # write-up lives here (or docs/writeup.md linked from it)
├── Makefile               # make extract / build / evals / serve
├── pyproject.toml         # uv-managed deps
├── .env.example           # REDSHIFT_HOST=... (real .env gitignored)
├── pipeline/              # 01_extract.py, 02_identity.sql, 03_marts.sql ...
├── semantic/              # data dictionary + metric definitions (YAML/MD)
├── mcp_server/            # the MCP server package
├── analysis/              # the two strategy-question analyses + charts
├── evals/                 # known-answer question set + runner
└── docs/                  # data-notes.md, architecture diagram, deck PDF
```

### Hygiene rules
- `.gitignore`: `.env`, `*.parquet` / `data/` (extracts may contain the client dataset),
  notebooks' output if noisy
- **Never commit credentials or raw data.** Repo ships code + docs; `make extract` rebuilds
  data from Redshift for anyone with credentials
- Commit early and often — a readable history shows how you work

### Share with Vi (at submission)
Option A — make it public:
```bash
gh repo edit reina-firme-strategy-engine --visibility public --accept-visibility-change-consequences
```
Option B — keep private, invite their reviewers (get GitHub usernames from your Vi contact):
```bash
gh repo add-collaborator reina-firme-strategy-engine <vi-username>
```
Then email your Vi contact the repo link + hours spent + deck (PDF attached or in `docs/`).
Prefer Option B if the dataset spec or any client-flavored details end up in the repo; ask your
Vi contact which they prefer — it's a fair question for them.

---

## 4. Demo script (20 min slot)

1. 30-second architecture picture: Redshift → marts → semantic layer → MCP → Claude
2. Live: ask Claude "Why is Sacramento utilization 40% below Atlanta?" — watch it plan,
   query, and answer; compare to your verified analysis
3. Live: one growth question ("Where's our biggest leakage market without an owned facility?")
4. Show the eval runner passing — the trust story
5. Fallback: recorded video of the same flow, pre-tested

## 5. Risks & cuts (if time runs short)
- Cut stretch MCP tools and the map visual first
- Do NOT cut: the two answered questions, the eval set, the recorded demo fallback
- If entity resolution is messier than expected, document the mess and resolve only what the
  two strategy questions need — the write-up rewards honest tradeoffs

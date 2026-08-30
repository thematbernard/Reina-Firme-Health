# Reina Firme Strategy Engine

Unify Reina Firme Health's fragmented data, put an LLM-queryable MCP server on
top of it, and use that to answer the two questions the Strategy team said take
weeks.

**Both questions are answered, and one of them turned out to be wrong.**

- **Where should we open next?** Sacramento — as an acute-care hospital, not
  another clinic. 55,183 members (50,618 active), **zero owned hospitals and zero owned urgent
  cares**, and members travel a **median 75.5 miles** for acute care (95.7% over
  30 miles), the worst access in the network by a wide margin.
  → [analysis/01_next_facility.md](analysis/01_next_facility.md)
- **Why is Sacramento utilization 40% below Atlanta?** **It isn't.** Size-matched
  clinics differ by **0.4%**, and the widest gap between *any two* of the 64
  owned clinics is **2.9%** (CV 0.68%). A 40% gap is not constructible from this
  data, and every normalized measure puts Sacramento *above* Atlanta.
  → [analysis/02_sacramento_vs_atlanta.md](analysis/02_sacramento_vs_atlanta.md)

---

## The problem, and what was measured

The brief names three deficiencies. Each is answered with a number, not an
adjective — full detail and method in
**[docs/verified-status.md](docs/verified-status.md)**.

| Brief says | Built | Measured |
|---|---|---|
| no unified identity | `marts.identity_xwalk` | **99.89% precision** overall (85.2% on the fuzzy tier, 3 independent estimators within 0.2pp); recall 3.6–100% by corruption type |
| no consistent shape | 3 marts + a generated semantic layer | Q1 and Q2 are each **one query, no joins** — down from 11 JOINs / 110 lines; **195x** faster than hand-assembly |
| no fast query path | DuckDB + MCP server | **2ms** vs 298ms raw vs 0.4s at source |

The honest caveat, stated up front: **Redshift at 0.1–0.2s was never the
bottleneck.** What collapsed from weeks to minutes is the *construction* of a
correct query, not its execution. The data contains traps — a randomly-assigned
`provider_id`, tables on different time windows, partner facilities inflating
denominators, savings hidden in the wrong column — that produce confidently
wrong answers. The marts make five of them structurally impossible.

## Architecture

A **mart** is a table modelled for a question rather than for a source system:
a fixed grain — one row per facility, per market, per patient-member link — with
the joins and business rules already applied. The three here exist because the
alternative was documentation: telling the agent how to assemble `raw.*`
correctly on every query. Their grains were chosen to retire specific measured
caveats, not to mirror source; see [semantic/dictionary.md](semantic/dictionary.md).

```
Redshift (read-only)
      │  make extract          23 of 24 base tables → parquet, 1.6 GB
      ▼
data/raw/*.parquet
      │  make marts            views + materialized marts, atomic swap, 1.06s
      ▼
data/warehouse.duckdb ──────────────────► data/portable/reina_marts.duckdb
   raw.*     23 views (full history)         marts only, 7.1 MB, PII-free
   marts.*   identity_xwalk    592K          (runs with no source access)
             facility_metrics  284
             market_summary     42
             _build_metadata     7  ← freshness provenance
      │
      │  make docs             semantic/schema.md GENERATED from the warehouse
      ▼
semantic/  dictionary.md (hand-written rules + measured caveats)
           schema.md     (generated: columns, types, date ranges, join paths)
           joins.json    (single source of truth, asserted orphan-free)
      │
      ▼
mcp_server/server.py    4 tools, read-only, row-capped, build-fingerprinted
      │  stdio (Claude Desktop) or streamable-http
      ▼
Claude
```

Source access is **read-only**, so marts cannot live at source. That is the
reason to materialize locally — it is the only place the correctness rules can
be *encoded* rather than merely documented. See
[ADR 0002](docs/decisions/0002-materialization-and-freshness.md).

## Quickstart

**Without source credentials** (7 MB artifact, both questions answerable):

```bash
uv sync
make portable          # if data/portable/ is absent and you have a warehouse
make serve             # stdio; or add to Claude Desktop via .mcp.json
```

**With Redshift credentials** (full history, `raw.*` available):

```bash
cp .env.example .env   # host, port, database, username, password
make check             # connectivity smoke test
make build             # extract → marts → docs → portable  (~1 hr, mostly extract)
make test              # 130 tests, ~11s
```

Then ask Claude: *"Where should we open our next facility?"*

> **Restart your MCP client after changing code or the semantic layer.** Servers
> start once per session, so edits do not reach a running process. Compare
> `make fingerprint` against the `[build …]` tag in the server's instructions;
> a mismatch means restart.

### Environment variables

| var | effect |
|---|---|
| `REINA_DB` | override the warehouse path; the server still detects full vs marts-only from the data |
| `REINA_LOG_LEVEL` | server log level, default `INFO`. Logs go to **stderr** — stdout carries the JSON-RPC frames on stdio, so nothing else may write there |

## Make targets

| target | what |
|---|---|
| `check` / `profile` | Redshift connectivity; schema + date-range profile |
| `extract` / `marts` / `docs` | pull to parquet; build marts; regenerate `schema.md` |
| `portable` | export the 7 MB PII-free marts-only warehouse |
| `build` | `extract` + `marts` + `docs` + `portable` |
| `test` | 146 tests: warehouse, marts, MCP guardrails, stdio transport, harness structure |
| `analysis` | re-run both strategy analyses and print every number |
| `identity-quality` | measure crosswalk precision and recall |
| `benchmark` | time marts vs raw vs Redshift |
| `evals` | agent-level evals via the Anthropic SDK *(needs an Anthropic key)* |
| `evals-cli` | same 11 cases via `claude -p` over real MCP stdio *(no API key)* |
| `serve` / `serve-http` | run the MCP server on stdio / HTTP |
| `demo` | attach a client to a visible `serve-http` server via `.mcp.http.json`, so tool calls and SQL stream live in a second pane |
| `fingerprint` / `golden` | print the build fingerprint; regenerate the tool-description golden |

## How to check the work

Nothing here asks to be taken on trust.

- **`make test`** — 130 tests, ~11s, no credentials. Covers every layer between
  the question and the answer: stdio transport, MCP guardrails, mart-to-source
  reconciliation, crosswalk invariants, documented time windows, and regression
  guards on each measured caveat.
- **`make analysis`** — every number in both write-ups, recomputed live.
- **Generated, not asserted** — `semantic/schema.md` is generated from the
  warehouse and `make test` fails if it is stale. An earlier hand-written version
  claimed columns that did not exist (`ops_facilities.name`,
  `ops_appointments.patient_id`) and the agent believed it and wrote broken SQL.
- **Negative-controlled** — the transport and PII-guard tests were verified to
  *fail* when the server cannot start, when the write guardrail is removed, and
  when PII is injected. One test initially passed when it should have failed; it
  was tautological, and is fixed.

## Key decisions

| decision | why | where |
|---|---|---|
| DuckDB + local snapshot, refreshed nightly | source is read-only; claims already lag a **median 67 days**, so nightly adds ~0.5% | [ADR 0002](docs/decisions/0002-materialization-and-freshness.md) |
| Generate the schema half of the semantic layer | prose column lists cannot be validated, and drifted | `pipeline/05_gen_schema_doc.py`, [verified-status](docs/verified-status.md) |
| Encode caveats as marts, not documentation | a rule the model must obey on every query is fragile; a column is not | `pipeline/sql/02_*.sql` |
| Validate with a cold agent before packaging | author-graded evals are weak evidence | [ADR 0001](docs/decisions/0001-agent-validation-strategy.md) |
| Plain SQL + `make`, not dbt | four marts and one entry point; dbt would add a dependency without changing the output | [docs/roadmap.md](docs/roadmap.md) |

## Assumptions and limitations

- **The dataset is near-uniform per facility.** Completed appointments across the
  64 owned clinics have CV 0.68%; EHR encounters agree independently at 1.27%.
  No facility-level *performance* question is answerable here. This is a property
  of the data, recorded as caveat C2 — not something to model around.
- **`ops_appointments.provider_id` is randomly assigned** — 1.2% agreement with
  the provider's own facility, i.e. chance across 84 sites. Unusable as a
  capacity denominator (caveat C1).
- **Distances are straight-line**, not drive time.
  `raw.external_drive_time_isochrones` is unused; Sacramento's 75.5 miles is
  almost certainly worse in drive time.
- **Two source tables are deliberately not mirrored 1:1**, so the warehouse
  carries 23 of the 24 source base tables. `outreach.communications_log` (4.6M
  rows of per-message delivery telemetry — channel, template, response class) is
  not extracted: campaign-execution detail does not bear on facility siting.
  `ehr.observations` is pre-aggregated in Redshift to patient x month x LOINC as
  `raw.ehr_observations_monthly`, so row-level vitals and labs are not
  recoverable without a re-extract. Both are declared in `pipeline/02_extract.py`.
- **The observations rollup did not pay for itself.** 70.8M source rows became
  47.8M — a 32% reduction, ~1.48 source rows per group — because patient x month
  x LOINC is nearly unique here. Nothing downstream consumes it: no mart or
  analysis references it. The aggregation cost row grain and bought neither space
  nor a consumer. Extracting at row grain, or dropping it outright as with
  `communications_log`, would both be more defensible than this middle ground.
- **Mart coverage was derived from n=2 questions, and the correctness guarantee
  stops at its edge.** The marts encode five measured caveats structurally, but
  only at the facility and market grains they cover. Anything else — clinical
  detail, the full 3-year claims history, any grain not modelled — drops to
  `raw.*`, where those same caveats revert to prose the agent must obey on every
  query. The structural guarantee is therefore strongest on the questions already
  answered by hand and weakest on the novel ones an LLM interface exists to serve.
  In production, mart selection would be driven by observed query logs, not by two
  questions supplied up front. `evals/cases.json` is skewed the same way (8 of 11
  cases orbit those two questions); `raw_navigation_prevalence` is the one case
  that deliberately probes the ungoverned `raw.*` path.
- **Agent evals: 9/11**, run via `make evals-cli` (`claude -p` over the real
  stdio MCP transport, `claude-opus-5`, single rep). Both `bad_premise` and both
  `unanswerable` cases passed — the four that matter most. Two failures, and they
  are not the same kind of thing:
  - `raw_navigation_prevalence` is a **real** failure: structurally correct
    (right join path, right coverage caveat) but the numbers were ~8% low from an
    undisclosed active-enrollment filter, and it used a broadened `I1x` code set
    (25.3%) instead of essential hypertension (16.3%). This is the off-mart
    `raw.*` path, which is the weakest path by design.
  - `staffing_denominator` is a **false positive in the grader**. The agent
    answered correctly from `providers_based` and explicitly refused the C1 trap
    — but said "…makes every clinic look like it has ~5,597 providers" while
    doing so, and the deterministic `must_not` check is a plain substring match.
    Left unfixed and reported as a failure rather than corrected-and-rerun; see
    [roadmap item 5](docs/roadmap.md).

  Single rep, so no variance figure. The SDK runner (`make evals`) still has
  never executed — the 9/11 measures Claude Code + this MCP server, which is the
  configuration the demo uses.
- **Freshness is bounded by the last extract.** The nightly refresh is specified
  and the mechanics are in place (atomic swap, provenance table); the scheduler
  itself is not built.

## Repo layout

```
pipeline/     00 connect · 01 profile · 02 extract · 03 load · 04 marts
              05 gen schema doc · 06 export portable · sql/ mart definitions
semantic/     dictionary.md (hand) · schema.md (generated) · joins.json
mcp_server/   server.py — the 4 MCP tools
marts         identity_xwalk · facility_metrics · market_summary · _build_metadata
analysis/     both strategy questions + reproducible SQL
evals/        agent eval harness · identity quality · query benchmark
tests/        130 tests across 6 files
docs/         verified-status.md · roadmap.md · decisions/ (ADRs) · data-notes.md
```

## Tools used

- **Claude Code (Opus 5)** for implementation, analysis and documentation
  throughout. Used heavily and deliberately.
- **A cold Claude subagent** as an uncontaminated validator: no repo access, MCP
  tools only, asked the two strategy questions blind. It reproduced the
  Sacramento decomposition independently, produced a stronger Q1 answer than the
  half-finished one it was checking, found three real errors in the semantic
  layer — and produced one confident, well-argued, **wrong** hypothesis, which is
  why its output was verified rather than adopted.
  ([ADR 0001](docs/decisions/0001-agent-validation-strategy.md))
- DuckDB, `redshift-connector`, `pyarrow`, `mcp` (official SDK), pytest, `uv`.

Every number in this repo was verified against the warehouse independently of
whatever produced it.

## What's next

See **[docs/roadmap.md](docs/roadmap.md)**. Highest value first: the nightly
refresh scheduler; the DOB-variant identity fix (the only recall failure mode
that produces *wrong* rather than missing links); `marts.member_360`; running the
agent evals; curated MCP tools; real drive time.

## Time spent

**Approximately 9–10 hours**, against a planned budget of 8–10 (`PLAN.md`).

Work happened in three sessions rather than continuously, so the calendar span
(2026-08-28 → 2026-08-30) overstates effort considerably. Derived from commit
clustering:

| Session | Span | Commits | Work |
|---|---|---|---|
| Fri 8/28 eve | 19:17–21:24 (~2.1h) | 3 | Connectivity, profiling, extract/load, first marts + MCP server |
| Sat 8/29 | 12:12–17:01 (~4.8h) | 15 | Semantic layer, both analyses, evals, marts, measurement, stdio tests, portable artifact, README, guardrail hardening |
| Sun 8/30 | ~1.5h | 1 | Deck, talk track, number-consistency pass |

Add roughly an hour of setup before the first commit (credentials, reading the
dataset spec, `PLAN.md`) that left no commit trail.

The largest interior gap is 8/29 13:18→15:03, which was the portable-artifact
step — real work, not a break. Session spans are therefore a fair proxy for
effort here rather than an upper bound.

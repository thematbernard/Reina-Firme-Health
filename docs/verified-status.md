# Verified status — measured, not assumed

The brief names three deficiencies. This file states what we built for each,
what we **measured**, and what remains unmeasured. Every number here is
reproducible from a `make` target. Anything not measured is marked as such and
never estimated.

| Brief says | Built | Status |
|---|---|---|
| no unified identity | `marts.identity_xwalk` | **Measured** — ~99.9% precision, recall 3.6–100% by corruption type |
| no consistent shape | 4 marts + semantic layer | **Measured** — Q1/Q2 each 1 query, 195–268x faster than hand-assembly |
| no fast query path | DuckDB + MCP | **Measured** — 293x vs Redshift; but see the caveat, latency was not the bottleneck |

Reproduce: `make identity-quality`, `make benchmark`, `make test` (152 tests, ~16s).

---

## 1. Unified identity — measured

591,712 patient↔member links, 87% of 680K EHR patients. "87% linked" is
*coverage* and says nothing about quality, so both halves were measured.

### Precision: ~99.9% overall, ~85% on the fuzzy tier

Method: the matcher uses first/last name, DOB, gender and zip. It never looks at
`address_line1`, `city`, or the PCP fields. Those held-out attributes should
agree for a true link at the rate they agree for *exact* matches (the ceiling),
and at the rate random pairs agree (the floor). Three independent signals:

| match_method | n | address | city | PCP |
|---|---|---|---|---|
| exact | 584,373 | 92.1% | 100.0% | 81.9% |
| exact_tiebreak | 2,802 | 92.8% | 100.0% | 82.6% |
| **fuzzy** | **4,537** | **78.4%** | **85.9%** | **69.8%** |
| random control | 20,000 | 0.0% | 6.1% | 0.0% |

`precision = (observed − floor) / (ceiling − floor)` gives **85.2% / 85.0% /
85.3%** across the three signals — agreement within 0.2pp, which is why the
estimate is trustworthy rather than a single lucky proxy.

- **fuzzy precision ≈ 85.2%** → **~673 of 4,537 fuzzy links are wrong**
- `exact_tiebreak` scores *at or above* `exact`, so the zip tiebreak logic is sound
- **overall crosswalk precision ≈ 99.89%** across all 591,712 links

### Recall: strong on name typos, weak on surname changes, dangerous on DOB

Method: take patients that currently match exactly (so the true answer is
known), corrupt the patient record the way real records are corrupt, re-run the
**shipped** matcher, and check whether the right member returns. n=3,000 each.

| corruption | recall | wrong links |
|---|---|---|
| firstname_typo | 100.0% | 0 |
| zip_missing | 100.0% | 0 |
| lastname_typo | 61.4% | 0 |
| married_name (surname + `-REYES`) | 54.9% | 0 |
| lastname_typo **and** zip_missing | 10.1% | 0 |
| **dob_day_transposed** | **3.6%** | **29** |

Three findings, all actionable:

1. **Surname changes are the weak spot** (61.4% / 54.9%). The fuzzy gate requires
   *exact last name OR matching zip*; a surname change breaks the first, so
   recovery depends on zip agreeing — and zip only agrees for 56.2% of exact
   matches. The 61.4% is exactly what that predicts, so the mechanism is
   understood, not mysterious.
2. **Compound corruption is near-fatal** (10.1%). Both gates fail together.
3. **DOB corruption is the only failure mode that creates *wrong* links.**
   Fuzzy matching blocks on exact DOB, so a transposed birthday sends the
   matcher hunting among people born on a different day, where name similarity
   alone can produce a false positive: 29 wrong out of 138 matches, i.e. **21%
   of the matches it did make were wrong**. Every other corruption fails safely.

**Recommended fix (not implemented):** add a DOB-variant blocking pass
(transpositions, ±1 day, swapped month/day) and require a higher similarity
threshold when both surname *and* zip disagree. That converts the dangerous
failure mode into a safe one.

## 2. Consistent shape — measured

Before: `raw.*` was 23 views mirroring Redshift's shape verbatim; one mart
existed. Answering one question took **11 JOINs across 110 lines**, and the cold
agent needed **29 tool calls** for two questions.

After: `marts.facility_metrics` (284 rows), `marts.market_summary` (42),
`marts.market_flows` (12,443), `marts.identity_xwalk` (592K). Q1 and Q2 are each
**one query, no joins** — including the *second half* of Q1. `market_summary`
answers "which market"; it collapses every hospital line into one `acute_*`
group, so "what services should it offer" previously needed a three-table raw
join. `market_flows` carries spend at member_city × care_city × service_line ×
network_status, which is also the only grain at which a multi-city catchment is
expressible: a Sacramento member treated in Stockton is out-of-market at city
grain and in-corridor at corridor grain.

Five documented caveats became structurally impossible rather than remembered:

| was a rule the agent had to obey | now |
|---|---|
| C1 — never use `ops_appointments.provider_id` as a denominator | `providers_based` sourced correctly |
| C5 — filter `ownership='owned'` | `ownership` a column at grain |
| R2 — window both sides of a comparison | every mart column pre-windowed to the same 12 months |
| OR denominator — use operating days, not 365 | `or_utilization_pct` computed once |
| R6 — savings live in `plan_paid` | both `allowed_amount` and `plan_paid` carried |

Full warehouse rebuild: **1.36s**.

## 3. Fast query path — measured, with an honest caveat

`make benchmark`, median of 3 reps, Redshift result cache **disabled**
(left on, Redshift reports ~40ms for a multi-million-row scan and the
comparison is meaningless).

| question | mart | DuckDB raw | Redshift | vs raw | vs Redshift |
|---|---|---|---|---|---|
| Q2 clinic comparison | 0.9ms | 18.4ms | 0.10s | 21x | 111x |
| Q1 market ranking | 0.4ms | 161.1ms | 0.21s | 359x | 469x |
| leakage by market | 0.2ms | 119.0ms | 0.14s | 614x | 716x |
| **all three** | **2ms** | **298ms** | **0.4s** | **195x** | **293x** |

Cold: mart 1.1ms, DuckDB raw 186ms, Redshift 0.43–0.48s.

**The caveat that matters: Redshift at 0.1–0.2s was never the bottleneck.**
Quoting "293x faster than Redshift" as the business case would be misleading.
The brief's complaint was not per-query latency — it was that a Strategy analyst
could not *get to* a correct query: no unified identity, no consistent shape, and
a set of traps (uniform provider assignment, mixed time windows, partner
facilities in the denominator, savings hidden in the wrong column) that produce
confidently wrong answers. What actually collapsed from weeks to minutes is the
**construction** of the query, not its execution.

Two honest disclosures:

- The marts precompute, so their query time excludes a **1.36s build**. Against
  the DuckDB raw path the build pays for itself after roughly a dozen questions;
  against Redshift, after three.
- The DuckDB numbers come from a local parquet snapshot (1.6GB). **This is a
  deliberate architectural decision, not a shortcut** — see
  [ADR 0002](decisions/0002-materialization-and-freshness.md). Source access is
  read-only, so a materialized cache is the only place the correctness rules can
  be encoded rather than merely documented. The snapshot is refreshed by a
  nightly job so each morning starts on current data.

  The cadence is justified by measurement, not preference: claims are not final
  in source until a **median 67 days** after service (p90 91, max 104 — ~7 days
  to submit, ~60 to adjudicate). A nightly refresh therefore adds ≤24h on top of
  an inherent ~67-day pipeline, about **0.5% of the latency already in the
  data**. Sub-daily refresh would add operational surface to chase a number
  nobody can act on faster.

  Freshness is observable rather than assumed: `marts._build_metadata` records
  `built_at`, per-source row counts, `max_event_date`, `days_behind_today`, and
  the correct incremental column per table. The mart swap is atomic (build to
  `.tmp`, then `Path.replace()`), so a refresh cannot expose a half-built
  warehouse to a live reader.

  The scheduler itself is specified but **not yet implemented** — see
  [roadmap item 1](roadmap.md). The one detail that would quietly corrupt the
  warehouse if missed: nightly deltas must key on the *landing* column
  (`processed_date`, `booked_at`, `updated_at`), never the event date, because a
  `service_date` delta would permanently drop every late-arriving claim.

## 4. MCP transport — measured

Previously the largest blind spot: every other test imports `server.py` and
calls the tool functions directly, so broken tool registration, JSON-RPC
framing, schema serialization or server startup would leave the suite green and
the demo dead.

`tests/test_stdio.py` (14 tests) spawns the server as a subprocess exactly as
Claude Desktop does, completes the initialize handshake, and round-trips every
tool through the protocol: all four tools advertised with correct parameter
schemas, `list_tables` / `describe_table` / `run_query` /
`get_data_dictionary` returning real content, the guardrail rejection arriving
as a normal tool result rather than breaking the session, SQL errors likewise,
and the 500-row cap (the largest payload the transport carries) arriving whole
and truncation-flagged.

**Negative-controlled.** The tests were verified to fail when the server cannot
start, when the write guardrail is removed, and when a tool description changes.
That last control initially *passed* when it should have failed — the test
derived both expected and actual from the same `server.py`, making it
tautological for drift. Fixed with a committed golden file
(`tests/golden/tool_descriptions.json`, `make golden`) so an interface change
must appear as a reviewed diff.

### Stale-server mitigation

A test cannot reach into another process, so no test can prove the server
running inside someone's Claude Desktop is current. This is not hypothetical:
**a session in this project was served a dictionary predating several
corrections, and it was caught only by accident** — MCP servers start once and
live for the whole session, so editor-side changes never reach them.

The server now reports a build fingerprint (sha256 over `server.py` +
`dictionary.md` + `schema.md`) in its `instructions`, which every client sees.
Compare it to `make fingerprint`; a mismatch means restart the client. Verified
to change when the semantic layer changes, not just when code does.

## 5. Agent evals — measured, 9/11

Run with `make evals-cli`: the 11 cases in `evals/cases.json` driven through
`claude -p` with `--mcp-config .mcp.json --strict-mcp-config`, so the agent
reaches the four tools over the **real stdio MCP transport**. Model
`claude-opus-5`, single rep, no `ANTHROPIC_API_KEY` — it uses the Claude Code
CLI's own credential. `evals/results.json` records the runner and a harness note.

| kind | passed | what it measures |
|---|---|---|
| `factual` | 2/2 | can it find a number at all |
| `analytical` | 3/5 | multi-step reasoning, denominators, time windows |
| `bad_premise` | **2/2** | does it refuse to invent a cause |
| `unanswerable` | **2/2** | does it admit missing data instead of substituting a proxy |

**The four cases that matter most all passed.** On `sacramento_40pct_gap` the
judge recorded: *"explicitly rejects the false premise with the right evidence
(size-matched clinics differ ~0.4%, max/min 1.029, CV 0.68% across 64 owned
clinics)… and invents no causal story for the nonexistent gap."*

### The two failures are different in kind

**`raw_navigation_prevalence` — a real failure.** Method sound, numbers wrong:
4,401 hypertension members and 27,153 linked against a verified 4,820 and 29,598
(~8% low, from an active-enrollment filter it did not disclose), and a headline
25.3% computed over a broadened `I1x` code set rather than 16.3% for essential
hypertension. The structural reasoning was right — clinical data only in
`raw.ehr_conditions`, joined via `marts.identity_xwalk`, with the partial-EHR
coverage caveat stated. This is the off-mart `raw.*` path, which the mart
guarantee explicitly does not cover, and this case exists to probe it.

**`staffing_denominator` — a false positive in the grader.** The agent answered
correctly: provider counts from `marts.facility_metrics.providers_based`,
cross-checked against `raw.ops_providers`, `ownership='owned'` and
`facility_type='clinic'` applied. It then wrote:

> I did **not** use `ops_appointments.provider_id`; per caveat C1 it is randomly
> assigned and makes every clinic look like it has ~5,597 providers.

`must_not` is a plain substring match, so naming the trap it avoided scored
identically to falling into it.

**Reported as a failure, deliberately.** `evals/README.md` commits to reporting
failures rather than tuning cases until they pass, and quoting an improved
number after adjusting a check that the suite had just caught misfiring would
violate the spirit of that. The honest statement is: **9/11 measured, of which
one failure is a known grader artifact with the transcript as evidence.**
Negation-aware matching is a roadmap item, not a patch to apply on the way to a
better score.

### What this does and does not establish

One disclosure on the build: 9/11 was measured before `marts.market_flows` was
added. Nothing in the suite depends on that mart, and no case was re-run to
produce a better number, but the honest statement is that the pass rate belongs
to the preceding build.

It measures **Claude Code plus this MCP server** — the configuration the demo
runs — not the model in isolation. `--runner sdk` drives a bare Anthropic loop
with `run.py`'s own `SYSTEM` prompt and in-process tool dispatch; it remains
unexecuted, and the two are not comparable. Single rep, so no variance figure.

One thing the cli runner closes that nothing else did: it is the only automated
check exercising the agent, the tools, **and** the stdio transport together.
`tests/test_stdio.py` covers the transport without an agent; `--runner sdk`
would cover the agent without the transport.

## Still unmeasured

| gap | why it matters | how to close |
|---|---|---|
| **Nightly refresh scheduler** | decision and mechanics settled (ADR 0002); only the cron/Airflow wiring is outstanding | see [roadmap item 1](roadmap.md) |
| **Agent tool-call count against marts** | the real "time to answer"; cold agent needed 29 calls against `raw.*`. The cli runner reports turns, not itemised tool calls | rerun the cold probe, or use `--runner sdk` |
| **Eval variance** | 9/11 is a single rep; one run cannot separate a real failure from sampling | `make evals-cli` equivalent at `--reps 3` |
| **SDK-runner pass rate** | 9/11 came from the cli runner; the sdk path is a different harness and is still unexecuted | export a key, `make evals` |
| **`marts.member_360`** | the crosswalk is still only a join hop; unified identity has no consumer | build it |
| **Fuzzy-tier precision by hand** | 85.2% is an estimator, not a graded sample | hand-label ~50 fuzzy links |

# Talk track — 60 minute Zoom

| Time | Segment | This doc |
|---|---|---|
| 0:00–0:15 | Executive presentation (slides only, **no demo**) | Part 1 |
| 0:15–0:35 | Live demo + technical deep-dive | Part 2 |
| 0:35–1:00 | Discussion and Q&A | Part 3 |

**Supersedes `docs/demo-script.md`**, which was written for a single 15-minute
slot with the demo interleaved. Keep that file for its numbers cheat-sheet; use
this one for structure.

**The format's key consequence:** in Part 1 there is no live agent. Slides 2 and
3 are no longer a fallback — they are how the findings land. Deliver them as
findings, not as previews of a demo.

---

# PART 1 — Executive presentation (15:00)

Slide budget. Rehearse against these; if you are 90 seconds late by slide 4 you
will lose the risks slide, which is the one that buys credibility.

| Slide | Length | Cumulative |
|---|---|---|
| 1 — The problem | 2:00 | 2:00 |
| 2 — Answer 1: Sacramento | 3:30 | 5:30 |
| 3 — Answer 2: the refusal | 3:00 | 8:30 |
| 4 — How it works | 2:00 | 10:30 |
| 5 — Why trust it | 1:30 | 12:00 |
| 6 — Business impact | 1:30 | 13:30 |
| 7 — Risks | 1:00 | 14:30 |
| 8 — What's next | 0:30 | 15:00 |

## Opening — say this almost verbatim (0:00–0:30)

> Reina Firme has 1.1 million members, 84 owned facilities, and a Strategy team
> that waits weeks for answers that are already sitting in the warehouse.
>
> I was asked two questions. In the next fifteen minutes I'm going to answer
> both. Then I'll show you the thing that produced the answers, and you can try
> to break it.
>
> One note — you have the deck. Slides 2 and 3 are the answers. If you read
> ahead, you'll get there before I do, and I'd rather you heard why they're
> non-obvious.

That last line does real work. They have the deck in hand and will skim it;
naming that turns a distraction into a shared joke and buys you their attention
for the next two minutes.

## Slide 1 — The problem (2:00)

Beats, in order:

1. **The shape of the business.** Integrated payer *and* provider. 1.1M members,
   84 owned facilities, ~200 partner, across Northern California, Greater
   Atlanta, Central Texas.
2. **The constraint that shapes everything.** The data is 24 tables across 6
   schemas in Redshift, and access is **read-only**. You cannot build anything
   at source.
3. **Why that matters.** Say this plainly, it sets up slide 4:

   > Read-only means the correctness rules can't live where the data lives. They
   > have to live somewhere else, or they live in a document nobody reads.

4. **The cost today.** "Where should we open next?" is a question that takes
   weeks, because an analyst hand-assembles joins across six schemas and hopes
   they got the traps right.

Land on one sentence:

> I built a small set of correct analytical marts, an MCP server so Claude can
> query them in plain English, and the tests that show it can be trusted.

**Do not** put an architecture diagram here. It comes on slide 4, after they
care.

## Slide 2 — Answer 1: Sacramento, acute care (3:30)

The single most important slide. Structure it as a narrowing funnel.

**(0:45) The headline.** Open in Sacramento — as an acute-care hospital, not
another clinic. 55,183 members (50,618 active), **zero owned hospitals, zero
owned urgent cares**.

**(1:00) The access outlier.** Walk the table, one column:

> Sacramento members travel a **median 75.5 miles** for acute care. Atlanta is
> 9.1. That is eight times the distance. **95.7%** of Sacramento's acute claims
> are served more than thirty miles from home.

Then the money line: **82.9%** of allowed dollars leave the market — about
**$228M a year** — against Atlanta's 31.0%.

**(0:45) Why Sacramento and not Oakland.** This is the beat that shows the work
was real, so do not skip it under time pressure:

> Oakland also has zero owned hospitals, so member count alone doesn't separate
> them. What separates them is fallback distance. Oakland sits 12.6 miles from
> owned hospitals in San Francisco and Fremont. Sacramento has no fallback. That
> one column is the decision.

**(1:00) What to build, and the non-obvious part.** The service-line split is
unusually clean:

- Surgery **$221.5M**, only 11.8% retained
- Cardiology **$113.5M**, 11.6% retained
- ER **$58.1M**, 11.8% retained
- Imaging, primary care, labs, behavioral — all already **~72% retained**

> Only the hospital lines are leaking. The clinics are doing their job. So the
> recommendation is **not another clinic** — it's ~200 beds and 12–14 ORs, built
> for surgery, cardiology and an emergency department.

Close the slide on the ED:

> The ED matters beyond its $58 million. Unplanned volume cannot travel 75
> miles. It's the only line where distance is a clinical risk rather than an
> inconvenience.

## Slide 3 — Answer 2: the tool refused the question (3:00)

The rhetorical high point of the presentation. Do not rush it.

**(0:30) Set the trap.** Read the question as it was given to you:

> "Why is utilization at our Sacramento clinic 40% below our Atlanta clinic of
> similar size?"
>
> I want to be careful here, because this is the answer I'm proudest of. It
> isn't.

**(1:00) The premise doesn't hold.** Across all 64 owned clinics, completed
appointments have a coefficient of variation of **0.68%** — the spread between
the busiest and quietest clinic in the entire network is **2.9%**.

> To produce a 40% gap you need a ratio of about 1.67. The widest ratio that
> exists anywhere in this data is 1.029. A 40% gap isn't unsupported — it isn't
> *constructible*.

**(0:30) Pre-empt "you averaged it away."** Name the pair:

> That's not an average hiding a bad clinic. I took the Sacramento and Atlanta
> clinics whose attributed panels are closest — 11,190 against 11,174, sixteen
> members apart — and compared them directly. The gap is 0.4%.

And the corroboration: an independent volume source, EHR encounters, gives
CV 1.27%. Two unrelated systems agreeing is not one bad extract.

**(0:45) The line the whole project rests on.** Slow down:

> A tool that wanted to please me would have invented a staffing shortage here.
> It would have been fluent, it would have been confident, and it would have
> been wrong. This one told me the question was wrong — and then pointed me at
> the real problem.

**(0:15) The kicker.** The sign reverses. Per attributed panel member,
Sacramento is **+27.9% above** Atlanta. Three of four denominators put
Sacramento ahead.

> Panel-normalized utilization shows a 3.18x spread across the network — which
> looks like a rich signal, and is entirely denominator variance, because the
> numerator barely moves. That's the trap a naive analysis walks into. It's
> probably where the 40% came from.

Bridge to slide 4:

> The real Sacramento problem is network composition. Which is slide 2. Here's
> how the tool knows the difference.

## Slide 4 — How it works (2:00)

**(0:30) The architecture, once.** Redshift → marts → semantic layer → MCP →
Claude. Three marts. Full rebuild in **1.06 seconds**.

**(1:00) Make it concrete — the best 30 seconds in the deck.** Say it as a
story, not a spec:

> `ops_appointments` has a `provider_id` column. It looks like exactly what you
> want for a staffing denominator. It's randomly assigned — 1.2% agreement with
> the provider's own facility, which is chance across 84 sites. Any agent that
> uses it reports a meaningless ~5,597 providers at every single clinic.
>
> We didn't document that trap and hope the model reads the docs. The mart
> sources provider counts from the right table and never exposes the bad column.
> We made the wrong answer **structurally unreachable**.

**(0:30) Generalize it.** Five documented caveats moved from "a rule the agent
must remember" to "impossible to express." And the query that produced every
number on slide 3 is a `WHERE` on one table — the pre-mart version needed five
raw tables joined together.

## Slide 5 — Why trust it (1:30)

**(0:30) Two layers, named.**

> 146 tests prove the *data* is true — mart grain, reconciliation back to
> source, guards that a retired caveat hasn't crept back. Fifteen seconds, no AI
> involved. Eleven eval cases prove the *agent* reaches the right conclusion
> through the tools. Those ran at **nine out of eleven**.

**(0:30) The eval design is the point.**

> Two of the eleven have false premises and two have no answer in the data.
> Those four are the most valuable cases in the suite, and **all four passed**.
> Slide 3 wasn't luck.

**(0:20) Then volunteer the failures — before anyone asks.**

> Of the two that failed, one is real: the raw-data case got the structure right
> and the numbers 8% wrong. The other is my grader's fault — the agent refused
> the trap correctly, said the trap's number out loud while explaining why it
> refused, and my substring check couldn't tell the difference. I could have
> fixed that and shown you ten out of eleven. I left it, because a number you get
> by adjusting the test after it fails isn't a measurement.

**(0:30) The part that usually surprises people.**

> Several tests pin the conclusions in this deck. There's a test asserting the
> size-matched pair has no gap. There's one asserting that recapture dollars
> alone would pick Atlanta, not Sacramento — so the write-up can't quietly drift
> into a stronger claim than the data supports. If the data changed such that
> Sacramento stopped being the answer, the build would fail.

## Slide 6 — Business impact (1:30)

**(0:45) The corridor.** Sacramento anchors a three-city corridor with Stockton
and Modesto: **102,540 active members**, comparable to Atlanta's 122,480, which
supports one 206-bed hospital. Recoverable: **$33.2M a year** in plan-paid.

**(0:45) The finding a naive analysis would miss.** Say it before anyone asks:

> Average allowed amount is essentially identical wherever care happens — $951
> owned, $957 partner, $955 out-of-network. A business case built on allowed
> dollars shows **no benefit at all**. The entire saving is in the share Reina
> Firme pays: 0.44 owned, 0.62 in-network partner, 0.80 out-of-network.
>
> If you take one methodological point from this: the savings live in
> `plan_paid`, not `allowed_amount`.

**Do not** say "293x faster than Redshift." If you have the instinct, replace it
with:

> What collapsed from weeks to minutes isn't query *execution* — Redshift was
> always fast. It's query *construction*.

## Slide 7 — Risks (1:00)

Rattle these off. Speed here reads as confidence, not evasion.

- **The evals are one rep.** 9/11, no variance figure yet, and it measures Claude
  Code plus this server rather than the model in isolation.
- **Distances are straight-line, not drive time.** 252 isochrone polygons sit
  unused. This *understates* Sacramento's disadvantage, so measuring it
  strengthens the case.
- **$33.2M assumes full recapture** at current owned cost ratios. It's a ceiling,
  not a forecast.
- **The guarantee stops at the mart edge.** Off-mart questions fall back to raw
  tables, where the caveats revert to prose.
- **This dataset is near-uniform.** CV 0.68% means no facility-level performance
  question is answerable here. That's a property of the data, not a modelling
  choice.
- **No capital cost, staffing, licensure or CON analysis.** This sizes the
  demand-side opportunity only.

## Slide 8 — What's next (0:30)

Six items, highest value first: nightly refresh scheduler; the DOB-variant
identity fix; `marts.member_360`; run the evals; curated MCP tools; real drive
time.

Hand off:

> That's the answer. Now let me show you the thing that produced it.

---

# PART 2 — Live demo + technical deep-dive (20:00)

| Block | Length |
|---|---|
| Framing | 1:00 |
| Live Q1 | 5:00 |
| Live Q2 | 5:00 |
| Deep dive | 7:00 |
| Buffer | 2:00 |

## Pre-flight (before the call, off the clock)

```
make server-info      # expect mode=full, fingerprint matching `make fingerprint`
make fingerprint      # these two MUST match
```

- [ ] Claude Code open, `reina-firme-analytics` connected, **stdio** transport
- [ ] `make serve-http` **NOT** running — open file-disclosure gap, and it isn't
      the demo path
- [ ] Terminal font large enough to read over Zoom screen-share
- [ ] Second window with `make test` ready to run
- [ ] Fallback recording to hand if an agent run stalls
- [ ] Working tree committed

## Framing (1:00)

> What you're about to see is a normal Claude session. The only thing that makes
> it different is one MCP server exposing four tools over a local warehouse.
>
> I'm going to ask it the same two questions I just answered. I have not
> pre-loaded the answers, and I can't control what it does. If it says something
> wrong, you'll see it, and we'll talk about why.

That last sentence is worth saying because it's true and because it makes
everything after it credible.

## Live Q1 (5:00) — type verbatim

```
Where should we open our next facility, and what services should it offer?
```

**Narrate the dead air — this is the skill.** As tool calls appear:

> It called `get_data_dictionary` first. That's the semantic layer handing it the
> canonical metric definitions, the valid join paths, and six measured data
> traps, before it writes a single line of SQL. It isn't guessing at column
> names — it's reading the ones generated from the warehouse.

As SQL appears, read it aloud. When the answer lands, compare it to slide 2 out
loud: same market, same reasoning, same recommendation.

> Fifteen minutes ago I told you Sacramento, acute care. It just got there on its
> own, in about ninety seconds, from plain English.

## Live Q2 (5:00) — type verbatim

```
Why is utilization at our Sacramento clinic 40% below our Atlanta clinic of
similar size?
```

Before you press enter, tell them what to watch for:

> Notice what I did — I asserted a fact in the question. Forty percent. Watch
> whether it accepts it.

Then let it work. When it refuses the premise, stop talking for a beat and let
that sit before you say anything.

## Technical deep-dive (7:00)

Four things, in this order.

**(2:00) The semantic layer.** Call `get_data_dictionary` and scroll it. Show
that it's two parts — hand-written business rules, then a *generated* schema
reference. Point at a caveat and say why it exists.

**(2:00) The trap, in the data.** Run it live:

```sql
SELECT count(*) FROM raw.ops_appointments a
JOIN raw.ops_providers p USING (provider_id)
WHERE p.primary_facility_id = a.facility_id;
```

> 1.2% agreement. Chance. This column is a landmine, and the mart doesn't expose
> it.

**(2:00) The guardrails.** Try a write and let it get rejected. Show the row cap.
Then the fingerprint:

```
make server-info
```

> MCP servers start once and live for the whole session, so an editor-side change
> never reaches a running server. That bit me during development — a session was
> served a stale dictionary and it was caught by accident. Now every client sees
> a build fingerprint it can compare against the repo.

**(1:00) The tests, then one eval live.**

```
make test
```

146 tests, ~15 seconds, deterministic. While it runs, say the conclusion-pinning
point from slide 5.

Then one eval case — about 30 seconds, and it shows the grading machinery that
`make test` cannot:

```
uv run python evals/run.py --runner cli --case sacramento_40pct_gap
```

> This is the same question you saw me ask live. The difference is that now it's
> graded — the judge gets the independently verified ground truth and checks
> three axes: are the numbers right, is the method sound, did it assert anything
> the data doesn't support. PASS needs all three.

Then show the full result: **9/11**, and name both failures as on slide 5.

**Do not run the whole suite live** — it's ~7 minutes and non-deterministic.

## If something breaks

| Failure | Move |
|---|---|
| Agent stalls >2 min | Cut to the fallback recording; keep talking |
| Agent gets it wrong | **Lean in.** Every tool call and its SQL is logged to stderr — pull it up and trace it. Traceability *is* the story |
| Says it can't answer | That's a pass, not a miss. Say so before they conclude otherwise |
| Server fingerprint mismatch | Restart the client. Cheaper than debugging live |

---

# PART 3 — Discussion and Q&A (25:00)

25 minutes is long. Have material ready rather than filling with hedges.

## Invite the unscripted question early

> Ask it something I haven't prepared for.

Set expectations first, so any outcome is a good outcome:

> If it tells you the data can't answer your question, that's the system working.
> Two of my eleven eval cases exist specifically to test that.

## Anticipated questions

**"How do I know it isn't making the numbers up?"**
Every tool call and the SQL behind it is logged. 146 tests reconcile the marts
back to source. And the conclusions in the deck are themselves regression-tested.

**"What happens when the data changes?"**
`marts._build_metadata` records build time, per-source row counts, and how far
behind today each source is. The nightly refresh is specified in ADR 0002 —
scheduler not built. Cadence is justified by measurement: claims aren't final in
source until a median 67 days after service, so nightly adds ≤24h to an inherent
67-day pipeline.

**"Could this work on our real data?"**
The architecture transfers; the numbers don't. This dataset is near-uniform
(CV 0.68%), which is why no facility-level performance question is answerable.
On real data that flatness disappears and the same marts would show real
variance.

**"Why not dbt / a real warehouse / Snowflake?"**
For four marts and one `make` target, dbt adds a dependency without changing the
output. Documented as a deliberate non-choice, not an oversight.

**"How accurate is the identity matching?"**
591,712 links, 87% of 680K patients. ~99.89% precision overall, ~85% on the fuzzy
tier. Recall is the honest weak spot: 100% on first-name typos, 61% on surname
typos, and **3.6% on a transposed date of birth** — the only failure mode that
produces *wrong* rather than missing links. Fix is specified, not built.

**"What's your eval pass rate?"**
9/11, single rep, via `make evals-cli` — `claude -p` over the real stdio MCP
transport, so it exercises agent, tools and transport together. Both bad-premise
and both unanswerable cases passed. One real failure on the off-mart raw path
(numbers 8% low from an undisclosed enrollment filter); one grader false positive
I left unfixed on purpose. No variance figure — it's one rep.

**"Why didn't you just fix the broken check?"**
Because then the number would be an artifact of having seen it fail. The repo
commits to reporting failures rather than tuning cases until they pass, and that
commitment is worth more than the extra point. Negation-aware matching is
roadmap item 5.

**"What would you do with another week?"**
Roadmap, in order. Lead with the DOB fix, because it's the one that's actively
dangerous rather than merely absent.

**"How long did this take?"**
**Approximately 9–10 hours**, across three sessions on 8/28, 8/29 and 8/30 —
against a planned budget of 8–10. Breakdown is in the README under *Time spent*.
Do not say "see the git log.""

## Close

> The deliverable isn't the Sacramento recommendation. It's that the next
> question — the one nobody's thought of yet — takes minutes instead of weeks,
> and comes with the receipts.

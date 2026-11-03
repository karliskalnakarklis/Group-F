# AI log: other parts (design, findings fixes, DDD analysis, report)

The code of both variants is logged in [`variant-a.md`](variant-a.md) and
[`variant-b.md`](variant-b.md). This file covers the places where we used AI
for anything else.

The prompts here are **summarised, not verbatim**. Most of these sessions were
long back-and-forth chats where we pasted parts of our own docs, asked
questions and corrected the answers, so a verbatim list would be long and not
very useful. We describe what we asked for and what we did with the result.

## What was done by us, not by the AI

To be clear about the split: the AI was a tool for drafting, writing code from
our spec and checking our text. The decisions are ours.

- **Both cuts.** Which services exist in A and B, which data each one owns,
  the leader pattern, the receipts and undo, the outbox to reporting, and the
  policy not to prepare for the change requests. We worked these out from the
  stakeholder quotes, the legacy schema and the lectures (modularity, data
  decomposition, granularity drivers).
- **The criteria** (`docs/criteria.md`), their weights and the C5 scale. Fixed
  and tagged `criteria-v1` before any variant code.
- **Code review and findings.** Every entry in [`findings.md`](findings.md) was
  found by us, by reading the generated code against the design and by our own
  manual tests (same request id sent twice, upgrade from v1 to v2 without a
  reset, `docker pause` on customers, stopping services by hand). The agent did
  not find any of them itself; B5 is the only one it noted, as a decision, and
  we decided it is a deviation.
- **Running the tests and measurements.** `make test-*`, `make conformance-*`,
  `make bench-*`, `make blast-*` and `make impact` were run and checked by us,
  and we compared the numbers with our hypotheses ourselves.
- **What gets fixed and what is accepted** as a known gap (for example A2, A3,
  B3, B4).
- **The recommendation and the trade-offs** in `docs/report.md`, and the final
  review of the DDD analysis.

## Sessions

### 1. Design of version 2, variant B

| Field | Value |
|-------|-------|
| Tool | Claude Code, in the Claude desktop app (Code tab), Windows 11 |
| Model and version | Claude Opus 5.5 (`claude-opus-5-5`) |
| Date(s) | 2026-11-03 |
| Who drove the session | Bozhidar Chobanov |
| Input given | `docs/design.md` (version 1), `docs/change-requests.md`, `docs/contract.md`, `variant-b/` at `v1` |
| Result | A draft of the variant B part of "Version 2" in `docs/design.md`, commit `01a9db4`. Karlis then merged it with the variant A part into one structure (`79d0258`). |

**What we asked for (summarised):** where CR1 and CR2 land in our variant B,
given that the cut must stay the same. We told it our own direction first: the
loyalty rule belongs to customers and must not be computed in till, the VAT
rates belong to selling, and no new service. We asked it to write it in the
same style as version 1 (tables per service, new data, changed calls, failure
behaviour).

**What we changed or checked:** we went through the draft against the change
requests rule by rule. Things we decided ourselves: that customers keeps its
own spend entries instead of asking till (so customers never calls till), that
a return of a customer's sale fails when customers is down instead of using a
second outbox, and that till stores the tier of a sale only as a value. The
merge with variant A was done by hand.

### 2. Fixes of the findings

| Field | Value |
|-------|-------|
| Tool | Claude Code, in the Claude desktop app (Code tab), Windows 11 |
| Model and version | Claude Opus 5.5 (`claude-opus-5-5`) |
| Date(s) | 2026-11-03 |
| Who drove the session | Bozhidar Chobanov |
| Input given | [`findings.md`](findings.md) with our description of each finding and the fix we wanted, `docs/design.md`, the code of both variants |
| Result | Fixes of A1, B1, B2: commit `34cd95d` (and the docs in `a71c3fb`). Fixes of A5, B6, B7: commit `5cc93b3` (and the docs in `1363d5c`). |

**What we asked for (summarised):** for each finding, implement the fix we
described (for example: key the receipts on a step key that the leader creates,
not on the client's `X-Request-Id`; key the ledger on `sale_id` / `return_id`;
add a migration step at start; call `take_back_points` before till opens its
transaction), update `docs/design.md` so that it matches the code, and do not
touch anything else.

**What we changed or checked:** we repeated the same manual test that found
each finding after the fix (same request id twice, upgrade from v1 to v2
without a reset, five returns with customers paused) and ran the acceptance and
conformance tests again. The text in the "Fix" column of `findings.md` is ours.

### 3. DDD analysis

| Field | Value |
|-------|-------|
| Tool | Claude (claude.ai, in a project with the course material, with access to our local assignment folder) |
| Model and version | Claude Opus 5.5 (`claude-opus-5-5`) |
| Date(s) | 2026-11-03 |
| Who drove the session | Bozhidar Chobanov |
| Input given | The course material on DDD (the "Cybermonday on Domain Driven Design" chapter, the short paper on integration patterns, the pointer to Vernon, *DDD Distilled*, lessons 1 to 4), `docs/design.md`, `ai-log/findings.md`, the blast results and the code of both variants |
| Result | A first draft of `docs/domain.md`, committed in `4d855ee` after our review |

**What we asked for (summarised):** fill in the six sections of the template
(subdomains, ubiquitous language, aggregates and invariants, the two context
maps, what the analysis changed) for both variants as they are, using the terms
from the course, and only work on that one file.

**What we changed or checked:** we checked every row of the invariant table
against the code (where the lock is, which service checks what) and every
relationship in the context maps against the internal calls in `design.md`.
The classification of the subdomains (selling and loyalty as core) and the
decision not to refine variant B in code after the analysis are ours. While
checking it, we noticed that the undo of `receive_stock` in till subtracts
stock without a check, the same kind of gap as A2.

### 4. Report and other docs

The analysis, the results table and the recommendation in `docs/report.md` were
written by us from our own measurements. We used Claude only for small things:
checking that the wording is clear and consistent with the other docs, and
spotting where a claim in the text had no evidence linked. It did not choose
the recommendation or the weights, and it did not produce any of the numbers.

## What we take from it

- The agent is good at turning a precise spec into code and docs in the same
  style. It is bad at noticing when the spec itself is wrong: A1, B1 and B2 were
  gaps in our design, and it implemented them exactly as written without asking.
- It optimises for what it can see. In B7 it kept fewer changed lines (good for
  `make impact`) and paid with a risk the tests could not see. So anything that
  affects a measurement needs a review of the "why", not only of the result.
- Nothing that the tests cannot see was found by the agent. Every such problem
  came from our code review and manual tests, which is why we treated those as
  the real verification step.

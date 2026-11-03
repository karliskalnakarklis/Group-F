# AI log: other uses of AI

Besides generating the code (see [`variant-a.md`](variant-a.md) and
[`variant-b.md`](variant-b.md)), we used a coding agent for the design,
for planning, for the findings, for running the measurements and for parts
of the report. Each of us summarises their own sessions below.

The prompts are **summarised, not verbatim**. Most of these sessions were
long back-and-forth chats where we pasted parts of our own docs, asked
questions and corrected the answers, so a verbatim list would be long and not
very useful. We describe what we asked for and what we did with the result.

## What was done by us, not by the AI

To be clear about the split: the AI was a tool for drafting, writing code from
our spec and checking our text. The decisions are ours.

- **Both cuts.** Which services exist in A and B, which data each one owns,
  the leader pattern, the receipts and undo and the outbox to reporting. We
  worked these out from the stakeholder quotes, the legacy schema and the
  lectures (modularity, data decomposition, granularity drivers). The policy
  not to prepare for the change requests was proposed by the agent and decided
  by us (see "Design of version 1" below).
- **The criteria** (`docs/criteria.md`), their weights and the C5 scale. Fixed
  and tagged `criteria-v1` before any variant code.
- **Code review and findings.** The code review was done together with the AI:
  for variant A in a Claude Code session (`b209e564`, see below), for variant B
  in a claude.ai session that read the code against the design and drafted
  B1-B5 (and the first version of the B1 fix in `reporting`). We decided what
  counts as a finding and what is only a difference from the design, reworded
  the rows (for example A1: the gap is in our design), checked each finding
  with our own manual tests (same request id sent twice, upgrade from v1 to v2
  without a reset, `docker pause` on customers, stopping services by hand), and
  decided which ones get fixed. The agent that generated the code did not
  report any of them itself; B5 is the only one it noted, as a decision.
- **Running the tests and measurements.** `make test-*`, `make conformance-*`,
  `make bench-*`, `make blast-*` and `make impact` were run and checked by us,
  and we compared the numbers with our hypotheses ourselves.
- **What gets fixed and what is accepted** as a known gap (for example A2, A3,
  B3, B4).
- **The recommendation and the trade-offs** in `docs/report.md`, and the final
  review of the DDD analysis.

## Sessions

The table below applies to the sessions listed with a session ID. The
other sessions have their own table.

Every session is kept by Claude Code under the session ID in the tables
below, and can be exported as a full transcript on request.

| Field | Value |
|-------|-------|
| Tool | Claude Code, in the Claude desktop app (Code tab), macOS |
| Model and version | Claude Opus 5.5 (`claude-opus-5-5`), in every session below |
| Date(s) | 2026-11-02 and 2026-11-03 |
| Who drove the sessions | Karlis Kalnakarklis |
| Input given | The repository as it was on `main` at the start of each session. The agent read `AGENTS.md`, `docs/assignment.md` and the other files it needed itself. |
| How I used the output | I read every change before it was committed. Several drafts were cut back to the template or reverted (see the tables). All commits were made without a co-author line. |

Times are local (CET).

### Design of version 1

| Session | When | What we asked | What the agent did | What we kept | Commit |
|---------|------|---------------|--------------------|--------------|--------|
| `856a898b` | 11-02, 20:33–21:52 | Explain the difference between variant A and B in business terms, then draft the design. | Explained the two cuts and corrected several of our assumptions: A does not reduce calls between services, it creates them; copies are optional in B, not required; B is not better in every way. Drafted the shared decisions and the variant A section. | The five shared decisions (taken from the template's guidance), the policy "no preparation for CR1 and CR2" (proposed by the agent, kept by us), the 4 services of variant A (people, stores, inventory, sales) and the all-or-nothing description. Everything the template did not ask for (extra explanations, a use case table) was removed at our request. | `9a779d4`, `1a9cf25` |
| `c2f7207f` | 11-02, 21:53 | How good are the shared part and variant A so far? | Rated them: good so far, needs additions. | Nothing to commit. | – |

### Planning and findings for version 1

| Session | When | What we asked | What the agent did | What we kept | Commit |
|---------|------|---------------|--------------------|--------------|--------|
| `c81a5103`, `3a48d29a`, `302efed1` | 11-03, 18:58–19:19 | What are the next steps to finish v1? | Wrote a to-do table from the assignment and the git history. Ran the tests of both variants locally. | A shorter table in the assignment's own wording, with the work split: Karlis reviews A, Bozhidar reviews B. | – |
| `b209e564` | 11-03, 19:21–19:46 | Review the variant A code against `design.md` and record what differs. | Read the code against the design and the contract and wrote the findings for A. Explained that fixing findings is optional and that findings are mainly what is actually wrong, not every difference from the design. Merged Bozhidar's B findings into the same structure. | One table per variant, short explanations. Finding A1 was reworded: the gap is in our design, and the agent's mistake was not to flag it. Decided which findings need a fix (A1, B1, B2). | `671335d` |
| `d39ef92f` | 11-03, 19:47 | Do we need to fix the findings now? | Advised fixing before tagging `v1`, so that the fixes are not counted in the `v1` → `v2` change (`make impact`, C2). | We followed this order. The fixes themselves were made by Bozhidar (`34cd95d`). | – |

### Fixes of the findings

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

### Measuring and tagging version 1

| Session | When | What we asked | What the agent did | What we kept | Commit |
|---------|------|---------------|--------------------|--------------|--------|
| `0d90c615` | 11-03, 20:05–20:14 | Run the v1 measurements on this machine and finish v1. | Ran tests, conformance, `bench` and `blast` for A, B and the baseline. Pulled Bozhidar's latest findings first, then committed the results and tagged `v1`. The tag was moved once to include his commit. | All six result files. | `d7aae2d`, tag `v1` |
| `d88927d8` | 11-03, 20:15 | What is left after v1? | Listed the open work: v2, the DDD analysis, the report, and the C4 script, which had not been written before v1 as `criteria.md` planned. | Plan for v2. | – |
| `fb52d80f` | 11-03, 20:17–20:28 | Is v1 finished? Then write the C4 script and start the report. | Wrote a first C4 script, a code-size script and a draft of the report. | Nothing: we reverted everything from this session. | – |

### Design of version 2

| Session | When | What we asked | What the agent did | What we kept | Commit |
|---------|------|---------------|--------------------|--------------|--------|
| `733a2157` | 11-03, 20:43–21:07 | Does v2 need a design, or do we only point the agent at the change requests? Then draft v2 for variant A. | Said the assignment does not require a v2 design outright, but that without one the agent makes the design decisions that we measure. Drafted v2 for variant A, then merged Bozhidar's v2 design for B into the same structure. | A shorter v2 part without diagrams, split into "Version 1" and "Version 2". From Bozhidar's B part we removed code details and choices made only to change fewer lines, so that B reads as a plan like A. | `79d0258` |

### Design of version 2, variant B

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

### Measuring version 2 and writing the report

| Session | When | What we asked | What the agent did | What we kept | Commit |
|---------|------|---------------|--------------------|--------------|--------|
| `722fc60e` | 11-03, 20:33–22:40 | Plan v2, run the v2 measurements, finish the C4 measurement and fill in the report. | Wrote the v2 to-do list and the build prompt for v2 (used by Bozhidar). Ran the v2 measurements, tagged `v2`, ran `make impact`. Wrote `bench/personal_data.sh` and ran it for both tags. Drafted report sections 2, 3, 4 (results), 7 (from Bozhidar's `domain.md`) and 8. Drafted Karlis's C5 rating from the design and the code. After both ratings were in, drafted sections 5 and 6. Removed leftover template guidance. | The measurements and the C4 script. Report sections 2–8. Karlis's C5 rating: drafted by the agent, checked and kept by Karlis; Bozhidar rated on his own. A first table for section 5 was reverted because we had not chosen a variant yet. The rule for adding up the weights in section 5 (the winner of a criterion gets its full weight, a tie splits it) was proposed by the agent, because `criteria.md` does not say how. The decision to write the C4 script after v2 and run it against both tags was made in this session. | `6c312cd`, `091ef38`, `13d8542`, `e8e55b9`, `641fd0b`, `55eb16d`, `31cae87`, `a0eb136`, `8885ad9`, tag `v2` |
| `2f071973` | 11-03, 22:43 | Is the assignment finished, apart from section 2 of the report? Then summarise the sessions for this file. | Listed what was missing (report sections 1 and 9, the reason for the C4 change, the empty "Changes after `criteria-v1`" table, this file). Read the session history and drafted this file. | This file. | – |

### DDD analysis

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

### Report sections 1 and 9, and this file

| Field | Value |
|-------|-------|
| Tool | Claude (claude.ai, in a project with the course material, with access to our local assignment folder) |
| Model and version | Claude Opus 5.5 (`claude-opus-5-5`) |
| Date(s) | 2026-11-03 |
| Who drove the session | Bozhidar Chobanov |
| Input given | `docs/report.md` with sections 2-8 already written, `ai-log/findings.md`, the AI logs, and some of Bozhidar's own messages as an example of his writing |
| Result | Drafts of report section 1 (recommendation) and section 9 (reflection), and a first draft of this file, which Karlis then extended with his sessions. Committed in `23d825a`. |

**What we asked for (summarised):** write section 1 and section 9 from
Bozhidar's point of view, short and without technical detail, based on the
results and the findings we already had; and for this file, summarise where we
used AI outside the code, without pasting the prompts word for word.

**What we changed or checked:** the recommendation itself (variant B) was
already decided in sections 5 and 6 before this session; the draft of section 1
only puts it into a few sentences for management. Section 9 was checked against
`findings.md`, so that every mistake it mentions is a real finding.

The other report sections (2-8) were drafted in Karlis's session `722fc60e`
(see "Measuring version 2 and writing the report" above). The numbers come from
our measurements, and the weights and the choice of variant are ours.

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

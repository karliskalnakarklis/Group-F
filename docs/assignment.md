# Assignment 1: Decomposing a monolith — two ways, measured

Deadline, assessment criteria and the AI policy are on Moodle. This document
describes the work itself.

## Scenario: Frischwerk

Frischwerk is a regional grocery chain with twelve stores in the Bern area.
Years ago it bought a point-of-sale (PoS) system from a US vendor and has
adapted it ever since. Today it is one application with one database: tills,
returns, purchasing, end-of-day and reports all read and write the same
tables. You can still see where it came from: US states in the addresses, a
US tax table, social security numbers of employees, plain-text passwords.

Every change now touches everything, and a database problem stops every till
in every store. Management has decided to split the system into services.
How to cut it is open, and nobody agrees:

> **Store manager:** "Checkout must keep working when the back office or
> reporting is down. A queue at the till costs customers."

> **Head of Finance:** "End-of-day and sales reports must reconcile to the
> cent, across stores, every evening."

> **Data Protection Officer:** "Customer and employee personal data in as few
> places as possible."

> **Head of Development:** "Two teams, four developers. Teams should deploy
> without waiting for each other, but I cannot run twenty services."

> **Product Owner:** "Swiss VAT and a loyalty programme are next on the
> roadmap."

Your group is asked for a recommendation that management can follow and
defend.

## What you build

You decompose the monolith in `baseline/` **twice**. Both variants fulfil the
same [contract](contract.md) and pass the same acceptance tests. They differ
in **how the boundaries are drawn**.

### Variant A: data-aligned

The services follow the legacy data: clusters of tables that belong together
by their foreign keys. Every legacy table has exactly one owning service, and
there is one source for every fact. Rules:
[`variant-a/README.md`](../variant-a/README.md).

### Variant B: capability-aligned

The services follow what the business does: the capabilities behind the use
cases (selling, taking returns, purchasing, running a till, reporting …).
Each service owns the data its capability needs, in its own model and its own
language. After the DDD lecture you refine it into bounded contexts. Rules:
[`variant-b/README.md`](../variant-b/README.md).

Everything else is your design decision: how many services, which data each
one owns, how services exchange data (synchronous calls or messages), how a
sale stays all-or-nothing when it spans several services, and what happens
when a service is down. Write these decisions down in `docs/design.md`.

### Version 1 and version 2

The [change requests](change-requests.md) CR1 (Swiss VAT) and CR2 (loyalty
tiers) are known from the start. You build each variant twice:

- **`v1`**: the contract as it is. The change request tests fail.
- **`v2`**: CR1 and CR2 implemented. All tests pass.

Between `v1` and `v2` you measure how far each change spread in each
variant. You may prepare your design for the change requests, because the
roadmap is known. If you do, decide it before `v1`, apply the same policy to
both variants, and write it down in `docs/design.md`. Preparation that costs
complexity in `v1` is part of what you compare.

### Coding agents are part of the method

Use an AI coding agent to generate the code. You write the specification
(`docs/design.md`), the agent writes the code, and you verify what it
produced. [`AGENTS.md`](../AGENTS.md) gives the agent the repository context.
You are accountable for every line you hand in, whoever typed it.

What is assessed is your design, your criteria, your evidence and your
reasoning. Passing the tests is necessary, but not sufficient.

## Steps

The plan follows the lectures: decomposition first, granularity next,
Domain-Driven Design last.

### 1. Set up (week 1)

Create your group's private copy of this repository and give the lecturer
access (see the [README](../README.md#getting-started)). Start the monolith,
run its tests, and look at its database schema (`baseline/monolith/schema.sql`)
and data (`shared/seed.json`).

### 2. Design both variants (week 1)

Fill in [`docs/design.md`](design.md) for both variants: services and the
data each one owns, how the use cases flow through the services, how failures
and partial failures are handled, and your policy for the change requests.
This is the specification you give the agent. Be precise: the agent will fill
every gap with a guess.

### 3. Define your comparison criteria first (week 1)

Before you generate any variant code, decide how you will compare the
variants. Fill in [`docs/criteria.md`](criteria.md), commit it and tag the
commit:

```bash
git tag criteria-v1
git push origin criteria-v1
```

The tag must be older than the first commit in `variant-a/` or `variant-b/`.
You may change the criteria later, but the report must say what changed and
why.

### 4. Version 1 (weeks 2–3)

Generate variant A and variant B with a coding agent. Record in `ai-log/`
which tool and model you used for each variant, what you gave the agent and
which prompts you used (see [`ai-log/README.md`](../ai-log/README.md)).

Verify both variants:

```bash
make up-a && make test-a && make conformance-a
make up-b && make test-b && make conformance-b
```

- The **acceptance tests** check the contract through the gateway.
- The **conformance checks** check the stack and the data-ownership rules in
  your compose file.
- Neither replaces your own **code review**. Read the generated code against
  your design. Record what the AI got wrong, and how you noticed, in
  [`ai-log/findings.md`](../ai-log/findings.md).

Measure both variants (see [Measuring](#measuring)), commit the results and
tag the commit `v1`.

### 5. Version 2 and the DDD analysis (weeks 3–4)

Implement CR1 and CR2 in both variants, with the agent. Verify with
`make test-a-v2` and `make test-b-v2`, measure again, commit and tag `v2`.
Then run `make impact` to see how far the changes spread, and commit its
result (it compares the tags, so it comes after `v2`).

After the DDD lecture, analyse both variants in
[`docs/domain.md`](domain.md): subdomains, the language of each service,
aggregates and their invariants, and a context map for each variant. You may
refine variant B along it; say what you changed.

### 6. Decide and reflect (CW 44)

Write [`docs/report.md`](report.md): your results against your criteria,
before and after the change requests, your hypotheses compared with the
results, your recommendation with its trade-offs, what would change it, and
your reflection on working with the coding agent.

### 7. Submit

Tag the commit you hand in and push all tags:

```bash
git tag a1-submission
git push origin --tags
```

Hand in the URL of your repository on Moodle.

## Measuring

| Command | What it measures | Result |
|---|---|---|
| `make bench-a` | latency, hops and services involved per use case | `bench/results/a-v1-bench.json` |
| `make blast-a` | stops each service in turn: which use cases still work | `bench/results/a-v1-blast.json` |
| `make bench-a LEVEL=v2`, `make blast-a LEVEL=v2` | the same, at version 2 | `…-v2-…json` |
| `make impact` | files and lines changed per service between the tags `v1` and `v2` | `bench/results/change-impact.md` |

The same for `b`, and for `baseline` as a point of comparison. Extend the
scripts, or add your own, for whatever your criteria need. Commit the scripts
and the raw results.

## Deliverables

All in your repository, at the tag `a1-submission`:

| What | Where |
|---|---|
| Design of both variants | `docs/design.md` |
| Comparison criteria, tagged `criteria-v1` before the first variant code | `docs/criteria.md` |
| Variant A and B, version 1 and version 2 | `variant-a/`, `variant-b/`, tags `v1` and `v2` |
| DDD analysis of both variants | `docs/domain.md` |
| AI log: tools, models, inputs, prompts | `ai-log/` |
| Findings: what the AI got wrong and how you noticed | `ai-log/findings.md` |
| Measurement scripts and raw results | `bench/` |
| Report with recommendation and reflection | `docs/report.md` |

## Rules

- Do not change `docs/contract.md`, `docs/change-requests.md`, `shared/` or
  `tests/`. The lecturer runs the original tests against your variants.
- Leave `baseline/` as it is; it is the point of comparison.
- One stack runs at a time. The gateway uses port 8000.
- Your variants must start with `make up-a` and `make up-b` on a machine that
  has only Docker, make and git installed.

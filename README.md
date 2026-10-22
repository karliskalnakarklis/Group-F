# Frischwerk PoS: decomposing a monolith

Starter repository for Assignment 1 of **SDA2 Software Architecture**, BFH.

Frischwerk, a grocery chain, wants to split its point-of-sale monolith into
services. Your group decomposes it twice with a coding agent: once along the
legacy data, once along the business capabilities. You define how to compare
the two, measure both before and after two change requests, and recommend
one.

- What to do: [`docs/assignment.md`](docs/assignment.md)
- What both variants must do: [`docs/contract.md`](docs/contract.md) and
  [`docs/change-requests.md`](docs/change-requests.md)
- Deadline, assessment criteria and AI policy: Moodle

## Getting started

### Prerequisites

- Docker (Docker Desktop on macOS and Windows)
- make
- git and a GitHub account

On Windows, work in WSL 2 or in Git Bash with make installed.

### 1. Create your group's private repository

This repository is a template. One group member creates the group's copy:

1. On GitHub, click **Use this template → Create a new repository**.
2. Choose your account as the owner and set the visibility to **Private**.
3. In the new repository, open **Settings → Collaborators** and invite the
   other group members and the lecturer (`shoehn`).

Then everyone clones the group's repository:

```bash
git clone git@github.com:<owner>/<your-repo>.git
cd <your-repo>
```

### 2. Run the monolith and its tests

```bash
make up-baseline
make test-baseline
make test-baseline-v2
make down
```

The first run downloads and builds the images and takes a few minutes.

The monolith implements the contract, so `make test-baseline` passes:
**41 passed**. It does not implement the change requests, so
`make test-baseline-v2` ends with an error: **27 failed, 26 passed**. If you
see these numbers, your setup works.

Try the measurements on the monolith too: `make up-baseline`, then
`make bench-baseline` and `make blast-baseline`. They give you the point of
comparison for your variants.

## The steps

1. Set up: private copy, monolith, tests (above).
2. Design both variants in `docs/design.md`.
3. Define your comparison criteria in `docs/criteria.md`, commit, tag `criteria-v1`.
4. Version 1: generate both variants with a coding agent, verify, measure, tag `v1`.
5. Version 2: implement the change requests in both, verify, measure, tag `v2`;
   analyse both variants with DDD in `docs/domain.md`.
6. Decide and reflect in `docs/report.md`.
7. Tag `a1-submission`, push all tags, and hand in the repository URL on Moodle.

Details and the timeline: [`docs/assignment.md`](docs/assignment.md#steps).

## Commands

`<stack>` is `baseline`, `a` or `b`. Only one stack runs at a time; the
gateway listens on port 8000. Starting a stack deletes all data and starts
from the seed.

| Command | What it does |
|---|---|
| `make up-<stack>` | reset the data, build and start a stack |
| `make test-<stack>` | acceptance tests, version 1 |
| `make test-<stack>-v2` | acceptance tests and change request tests, version 2 |
| `make conformance-<stack>` | stack and data-ownership rules in the compose file |
| `make bench-<stack>` | latency, hops and services per use case → `bench/results/` |
| `make blast-<stack>` | stop each service in turn, record which use cases still work → `bench/results/` |
| `make impact` | how far the change requests spread between the tags `v1` and `v2` |
| `make logs` | follow the logs of the running stack |
| `make down` | stop the running stack |
| `make test-image` | rebuild the test image |

Add `LEVEL=v2` to `bench` and `blast` for the measurements of version 2.
To run a single test file: `./tests/runner.sh a pytest tests/acceptance/test_sales.py`.

## Repository layout

```
├── README.md
├── AGENTS.md              context for coding agents
├── Makefile
├── docs/
│   ├── assignment.md      scenario, variants, steps, deliverables
│   ├── contract.md        external behaviour, version 1
│   ├── change-requests.md CR1 Swiss VAT, CR2 loyalty tiers (version 2)
│   ├── design.md          template: your specification for the agent
│   ├── criteria.md        template: your comparison criteria
│   ├── domain.md          template: DDD analysis of both variants
│   └── report.md          template: results, decision, reflection
├── ai-log/                how you used AI, and what it got wrong
├── shared/seed.json       the legacy data (fictional)
├── baseline/              the monolith: FastAPI + MariaDB with the legacy schema
├── variant-a/             your variant A: data-aligned
├── variant-b/             your variant B: capability-aligned
├── tests/                 acceptance tests, change request tests, conformance check
└── bench/                 measurement scripts and results/
```

## Contact

Sebastian Höhn, Bern University of Applied Sciences (BFH).

# AGENTS.md

Context for coding agents working in this repository.

## What this repository is

A teaching project. A group decomposes a point-of-sale monolith into services
twice, along two different decomposition strategies, and compares them. You
implement one variant at a time, from the group's specification.

## Sources of truth, in this order

1. [`docs/contract.md`](docs/contract.md): external behaviour (gateway API,
   rules, errors, call log, data ownership). For version 2 also
   [`docs/change-requests.md`](docs/change-requests.md). **Binding.**
2. The rules of the variant: [`variant-a/README.md`](variant-a/README.md) or
   [`variant-b/README.md`](variant-b/README.md). **Binding.**
3. [`docs/design.md`](docs/design.md): the group's design. Follow it. If it
   contradicts 1 or 2, or leaves a decision open, stop and ask. If you cannot
   ask, decide, and add the decision to `docs/design.md` under "Decisions
   taken by the agent" so that the group can review it.

## Layout

```
docs/          contract.md and change-requests.md (binding), design.md (the spec), assignment.md
shared/        seed.json: the legacy data, one key per legacy table (read-only)
baseline/      the monolith: one FastAPI service and one MariaDB with the legacy schema
variant-a/     variant A goes here: docker-compose.yml + one folder per service
variant-b/     variant B goes here: docker-compose.yml + one folder per service
tests/         acceptance tests, change request tests, conformance check, test runner (read-only)
bench/         measurement scripts and results/
ai-log/        the group's log of AI use
```

The monolith in `baseline/` implements the whole contract (version 1). Read it
to understand the behaviour; do not change it.

## Do not change

- `tests/`
- `shared/`
- `docs/contract.md`, `docs/change-requests.md`
- `baseline/`

If a test seems wrong, report it to the group; do not change it, and do not
write code that detects the test environment.

## Conventions

- Python 3.11 or newer with FastAPI is recommended; other languages are
  allowed per service.
- One folder and one `Dockerfile` per service, inside the variant folder. A
  shared code folder (for example `common/`) is allowed; it counts as its own
  folder in `make impact`.
- The variant's `docker-compose.yml` sets `name: pos`. Only the service
  `gateway` publishes a port (`8000:8000`).
- Every service answers `GET /health` with `200`, has a compose
  `healthcheck`, and mounts the volume `calllogs` at `/logs`.
- Every service loads its initial data from `shared/seed.json` at start,
  mounted into the container (for example `volumes: ["../shared:/shared:ro"]`).
  Do not copy seed data into the code.
- Data stores and their networks follow "Data ownership" in the contract;
  stores carry the labels `pos.role` and `pos.owner`, and in variant A the
  application services carry `pos.tables`.
- Every service writes the call log described in the contract and passes
  `X-Request-Id` on.

## Commands

Prerequisites are Docker, make and git. Tests run in a container.

| Command | What it does |
|---------|--------------|
| `make up-a` / `make up-b` | reset all data, build and start the variant |
| `make test-a` / `make test-b` | acceptance tests, version 1 |
| `make test-a-v2` / `make test-b-v2` | acceptance tests and change request tests, version 2 |
| `make conformance-a` / `make conformance-b` | stack and data-ownership rules in the compose file |
| `make bench-a`, `make blast-a` | measurements, written to `bench/results/` |
| `make logs` | follow the logs of the running stack |
| `make down` | stop the running stack |

## Definition of done for a variant

- `make up-a` (or `up-b`) starts the stack from a clean checkout.
- Version 1: `make test-a` passes. Version 2: `make test-a-v2` passes.
- `make conformance-a` (or `conformance-b`) passes.
- `make bench-a` runs without "no call log found".
- The code does what `docs/design.md` says. Where you deviated, say so.
- Nothing outside the variant's folder was changed, unless the group asked.

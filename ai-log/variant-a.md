# AI log: variant A (data-aligned), version 1

| Field | Value |
|-------|-------|
| Tool | Claude Code, in the Claude desktop app (Code tab), Windows 11, auto mode |
| Model and version | Claude Opus 5.5 (`claude-opus-5-5`) |
| Date(s) | 2026-11-03 |
| Who drove the session | Karlis Kalnakarklis |
| Input given | `docs/design.md` at commit `81236c8`. The agent also read `AGENTS.md`, `docs/contract.md`, `variant-a/README.md`, `variant-b/README.md`, `docs/domain.md`, the `Makefile`, the monolith in `baseline/`, `shared/seed.json`, the acceptance tests and helpers in `tests/`, the conformance check and the scripts in `bench/`. |
| Prompts | One prompt for both variants, see below. |
| Manual changes | None so far. Everything in commit `2c1767a` was written by the agent. |

## Prompts

1. (the only prompt for the implementation, the same session as variant B)

   > Read AGENTS.md and follow it. Implement version 1 of both variants, A then B, from docs/design.md. Commit each variant when it meets the definition of done. Don't tag or push.

## What the agent produced

Commit `2c1767a` "Implement variant A (data-aligned), version 1":

- `variant-a/docker-compose.yml`: gateway, `people`, `stores`, `inventory`,
  `sales`, one MariaDB 11.4 per service (`people-db`, `stores-db`,
  `inventory-db`, `sales-db`), each on its own network with its owner.
- `variant-a/common/`: call log and request id (`calllog.py`), calls between
  services with the 2 s timeout and the undo of earlier steps, and the
  receipts and undo (`db.py`, table `applied_steps`, `POST /internal/undo`).
- One folder per service with `app.py`, `Dockerfile` and `requirements.txt`.
- A new section "Decisions taken by the agent" at the end of
  `docs/design.md` (common decisions and the variant A part).

## How the agent verified it

- `make conformance-a`: 43 passed, 0 failed.
- `make up-a`, then `make test-a`: 41 passed.
- `make bench-a`: runs; checkout 7 hops, the same number as the sequence
  diagram, which shows that `X-Request-Id` is passed through every service.
- Manual checks against the running stack:
  - `take_stock` called twice with the same request id changes the stock
    once; the undo gives the stock back; a second undo changes nothing; a
    `take_stock` that arrives after its undo is refused (`409`).
  - `add_points` and its undo.
  - `sales` stopped: closing a register answers `503`, and the session is
    open again afterwards.
  - `people` stopped: checkout answers `503`, and no stock is taken.
- After removing two unused imports, the full sequence ran again from a
  clean start (`up-a`, `test-a`, `conformance-a`, `bench-a`) before the
  commit.

## Not verified by the agent

- Two checkouts of the last item at the same time, and two returns of the
  same sale at the same time (the code locks the rows, but no concurrent test
  was run).
- A real timeout between services (only the undo after an error and the
  undo arriving before the step were tried, by calling the services
  directly).
- `make blast-a` was not run.
- The bench result `bench/results/a-v1-bench.json` was produced but not
  committed (it is outside the variant folder); there is no `v1` tag yet.

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

## Version 2 (CR1, CR2)

| Field | Value |
|-------|-------|
| Tool | Claude Code, in the Claude desktop app (Code tab), Windows 11, auto mode |
| Model and version | Claude Opus 5.5 (`claude-opus-5-5`) |
| Date(s) | 2026-11-03 |
| Who drove the session | Bozhidar Chobanov |
| Input given | `docs/design.md` at commit `79d0258` ("Design for v2: variant A, variant B merged into one structure"). The agent also read `AGENTS.md`, `variant-a/README.md`, `docs/change-requests.md`, `docs/contract.md`, `tests/cr/`, the `POS_LEVEL`-dependent parts of `tests/acceptance/`, `tests/pos.py`, `tests/conformance/ownership.py`, all service code in `variant-a/`, `variant-a/docker-compose.yml`, the `Makefile` and `shared/seed.json` (products 1 and 56, customers). |
| Prompts | One prompt for both variants, see below. |
| Commits | "Implement version 2 of variant A (CR1, CR2)", made by the agent; this log entry is part of that commit. |
| Manual changes | None so far. |

### Prompt

1. (the prompt for the implementation of both variants; the session first
   asked whether the agent may commit, may touch variant A, and how to get
   the new design; the answers were "Agent commits", "A then B", and "Pull
   main, stay on main")

   > We have a new design.md version. Read through it to understand how to do the "step 2 build" part again + the ai log. I've rollbacked on those files.
   > Read AGENTS.md and follow it. Implement version 2 of both variants, A then B, from docs/design.md (CR1 and CR2 from docs/change-requests.md). Commit each variant when it meets the definition of done for version 2. Don't tag or push.
   > Run a final check if everything is done afterwards and give me a summary table

### What the agent produced

- `variant-a/inventory/app.py`: `GET /internal/products` answers `category`.
- `variant-a/sales/app.py`: `vat_table`, `vat_category`, `ticket_vat`,
  `item_list.vat_rate`, `ticket_system.tier` and `.points_rate`
  (`tax_rate` written as `0`); VAT per rate in the sale, the session totals
  and the sales report; spend and tier from its own tables; points by tier;
  `take_back_points` on a return of a customer's sale; the new call
  `GET /internal/customers/{id}/spend`.
- `variant-a/people/app.py`: `GET /customers/{id}` asks sales for `tier`
  and `spend_12m`; the new step `take_back_points`
  (`POST /internal/customers/{id}/points/take-back`) and its undo.
- `variant-a/stores/app.py`: the Z-report passes `vat` from sales.
- `docs/design.md`: "Decisions taken by the agent (version 2)" → "Variant A".
- No change to the gateway, `common/` or `docker-compose.yml`.

### How the agent verified it

- `make up-a`: all containers healthy.
- `make test-a-v2`: 53 passed. Run as `make test-a-v2 RUN="bash tests/runner.sh"`,
  because GNU Make on this Windows machine cuts the path of `tests/runner.sh`
  at the space in the folder name before any test runs; no file was changed
  for this.
- `make conformance-a`: 43 passed, 0 failed.
- The bench (`bench/measure.py` with `POS_LEVEL=v2`, through the same
  runner) ran without "no call log found"; its output was written outside
  the repository, so `bench/results/` is unchanged.
- Manual checks against a fresh stack:
  1. Sale of 2 × product 1 (Dairy) and 1 × product 56 (Bathroom): `vat` =
     2.6 % (net 17.52, vat 0.46, gross 17.98), then 8.1 % (17.57, 1.42,
     18.99); total 36.97, tax 1.88, as computed by hand.
  2. Sale with customer 1 (total 27.98): bronze, 27 points;
     `GET /customers/1`: points 33 → 60, `spend_12m` 27.98.
  3. Return of product 56 from that sale (refund 18.99): points 60 → 42,
     `spend_12m` 8.99.
  4. Z-report of register 2 and sales report of store 1: the same `vat` and
     `tax_total` (3.53).
  5. `sales` stopped: `GET /customers/1` answers `503 sales unavailable`, as
     the design says; after a restart it answers `200`.
  6. Never below 0: a customer whose points were set to 5 directly in
     `people-db` returned goods worth 18 points and ended at 0; the receipt
     of `take_back_points` keeps 5.

### Not verified by the agent

- The undo of `take_back_points` (after a failure of sales' own transaction
  or a timeout).
- Silver and gold, and a return of a silver sale, only through `tests/cr/`.
- Two sales of one customer at the same time (accepted in the design).
- `make blast-a` and `make impact` were not run.

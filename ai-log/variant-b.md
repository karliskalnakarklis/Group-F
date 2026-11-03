# AI log: variant B (capability-aligned), version 1

| Field | Value |
|-------|-------|
| Tool | Claude Code, in the Claude desktop app (Code tab), Windows 11, auto mode |
| Model and version | Claude Opus 5.5 (`claude-opus-5-5`) |
| Date(s) | 2026-11-03 |
| Who drove the session | Karlis Kalnakarklis |
| Input given | `docs/design.md` at commit `81236c8`, the same session and files as variant A (see [`variant-a.md`](variant-a.md)). Variant A was already committed (`2c1767a`) when B was written; the agent copied `variant-a/common/` and the gateway as a starting point. |
| Prompts | One prompt for both variants, see below. |
| Manual changes | None so far. Everything in commit `b27c80f` was written by the agent. |

## Prompts

1. (the only prompt for the implementation, the same session as variant A)

   > Read AGENTS.md and follow it. Implement version 1 of both variants, A then B, from docs/design.md. Commit each variant when it meets the definition of done. Don't tag or push.

## What the agent produced

Commit `b27c80f` "Implement variant B (capability-aligned), version 1":

- `variant-b/docker-compose.yml`: gateway, `till`, `purchasing`,
  `customers`, `reporting`, one MariaDB 11.4 per service (`till-db`,
  `purchasing-db`, `customers-db`, `reporting-db`), each on its own network
  with its owner.
- `variant-b/common/`: copied from variant A, with one addition: the
  environment variable `DB_ISOLATION` sets the isolation level of a
  service's database sessions (used by till, `READ COMMITTED`).
- One folder per service with `app.py`, `Dockerfile` and `requirements.txt`.
  Tables use the business names from the "Language" table of the design
  (`shifts`, `sales`, `sale_lines`, `payments`, `stock`, `price_list`,
  `suppliers`, `purchase_orders`, `customers`, `sale_entries`, ...).
- till: the ledger outbox with delivery right after the commit and a retry
  every 2 s; the price list pulled from purchasing every 60 s.
- The variant B part of "Decisions taken by the agent" in `docs/design.md`.

## How the agent verified it

- `make conformance-b`: 26 passed, 0 failed.
- `make up-b`, then `make test-b`: 41 passed (first run, no fixes needed).
- `make bench-b`: runs; checkout 3 hops (till, customers, reporting), as in
  the sequence diagram.
- Manual checks against the running stack:
  - `reporting` stopped: a sale still answers `201`; one row waits in the
    outbox; after `reporting` is started again the row is delivered within
    a few seconds, and the sales report of store 1 counts the same number of
    sales as till's own table (110).
  - `purchasing` stopped: checkout still works; the product lookup answers
    `503 purchasing unavailable`.
  - Three goods receipts of the same order at the same time: one `200`, two
    `409`, stock increased once by the ordered quantity.

## Not verified by the agent

- A sale or return running at the same moment as the close of its register
  (the shared lock on the shift and the `READ COMMITTED` setting are meant
  to handle it, but no concurrent test was run).
- `customers` stopped during a sale with a customer, and the undo of
  `earn_points` after a timeout.
- The 60 s price list refresh was not observed in the logs.
- `make blast-b` was not run.
- The bench result `bench/results/b-v1-bench.json` was produced but not
  committed; there is no `v1` tag yet.

## Version 2 (CR1, CR2)

| Field | Value |
|-------|-------|
| Tool | Claude Code, in the Claude desktop app (Code tab), Windows 11, auto mode |
| Model and version | Claude Opus 5.5 (`claude-opus-5-5`) |
| Date(s) | 2026-11-03 |
| Who drove the session | Bozhidar Chobanov |
| Input given | `docs/design.md` at commit `79d0258` ("Design for v2: variant A, variant B merged into one structure"). The agent also read `AGENTS.md`, `variant-b/README.md`, `docs/change-requests.md`, `docs/contract.md`, `tests/cr/`, the `POS_LEVEL`-dependent parts of `tests/acceptance/`, `tests/pos.py`, all of `variant-b/`, the `Makefile` and `shared/seed.json` (products 1 and 56, customers). An earlier draft of the variant B v2 design (commit `01a9db4`) was written by the agent in the same session, from a design prompt by Bozhidar Chobanov; `79d0258` is the group's merged version of it. |
| Prompts | One prompt for both variants, see [`variant-a.md`](variant-a.md), "Version 2". |
| Commits | "Implement version 2 of variant B (CR1, CR2)", made by the agent after variant A (`faa28df`); this log entry is part of that commit. |
| Manual changes | None so far. |

### What the agent produced

- `variant-b/purchasing/app.py`: `GET /internal/price-list` answers
  `category`.
- `variant-b/till/app.py`: `vat_rates`, `category` in the price list copy,
  `vat_rate` per sale line, `sale_vat`, `tier` on the sale (in place of
  `tax_rate`); VAT per rate in the sale, the Z-report and the ledger
  payload; gross refund; the `take_back_points` step on a return of a
  customer's sale.
- `variant-b/customers/app.py`: `spend_entries`; tier and points by tier in
  `earn`; the new call `take-back` and the undo of both steps; `tier` and
  `spend_12m` on a customer.
- `variant-b/reporting/app.py`: `sale_entry_vat` and `vat` in the sales
  report.
- `docs/design.md`: "Decisions taken by the agent (version 2)" → "Variant B".
- No change to the gateway, `common/` or `docker-compose.yml`.

### How the agent verified it

- `make up-b`: all containers healthy.
- `make test-b-v2`: 53 passed (run with `RUN="bash tests/runner.sh"`, for
  the same path problem as in variant A; no file was changed for this).
- `make conformance-b`: 26 passed, 0 failed.
- The bench (`bench/measure.py` with `POS_LEVEL=v2`) ran without "no call
  log found"; its output was written outside the repository.
- Manual checks against a fresh stack, with the same requests as in variant A:
  1. Mixed sale: `vat` 2.6 % (17.52 / 0.46 / 17.98), then 8.1 % (17.57 /
     1.42 / 18.99); total 36.97, tax 1.88.
  2. Sale with customer 1 (27.98): bronze, 27 points; points 33 → 60,
     `spend_12m` 27.98.
  3. Return of product 56 (18.99): points 60 → 42, `spend_12m` 8.99. A
     customer whose points were set to 5 in `customers-db` ended at 0 after
     a return worth 18 points.
  4. Z-report of register 2 and sales report of store 1: the same `vat` and
     `tax_total` (3.53).
  5. `customers` stopped: a sale without a customer answered `201`; a return
     of a sale of customer 1 answered `503 customers unavailable`, no return
     was stored and no stock was given back; after a restart the customer's
     points and spend were unchanged.

### Not verified by the agent

- The undo of `take_back_points` after till's own transaction fails or after
  a timeout of the call.
- Silver and gold, and a return of a silver sale, only through `tests/cr/`.
- Two sales of one customer at the same time (accepted in the design).
- The 60 s refresh of the category was not observed.
- `make blast-b` and `make impact` were not run.

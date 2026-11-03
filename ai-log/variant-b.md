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

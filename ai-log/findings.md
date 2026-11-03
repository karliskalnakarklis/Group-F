# Findings: what the AI got wrong

> One row per finding. "How found" is one of: acceptance test, conformance
> check, code review, measurement, other (say what). Link the commit that
> fixed it.

## Variant A

| # | Variant | What the AI produced | Why it is wrong or risky | How found | Fix (commit) |
|---|---------|----------------------|--------------------------|-----------|--------------|
| A1 | A | | | | |

## Variant B

Reviewed by Bozhidar Chobanov: every file in `variant-b/` read against
`docs/design.md` (variant B and the common decisions) and `docs/contract.md`.

| # | Variant | What the AI produced | Why it is wrong or risky | How found | Fix (commit) |
|---|---------|----------------------|--------------------------|-----------|--------------|
| B1 | B | reporting recorded each ledger entry with an `applied_steps` receipt keyed on (`X-Request-Id`, step), and answered "already done" for a known key (`reporting/app.py`, `record_sale`, `record_refund`). This follows our design to the letter. | The contract lets the client choose `X-Request-Id`. Two sales sent with the same id (a till that retries, a buggy client) both commit in till, but reporting finds the receipt of the first and answers `200` for the second without writing it; till marks the row delivered. The Z-report then counts both sales and the sales report one, with no error and nothing left in the outbox: exactly the silent mismatch C5 is about. The gap is in our spec; the agent did not question it. | code review (the tests cannot see it: `tests/pos.py` sends a new id with every request) | reporting keys ledger entries on `sale_id` / `return_id` (`INSERT IGNORE` on the primary key), keeps no receipts and has no undo; `docs/design.md` updated. Commit: _fill in_ |
| B2 | B | `earn_points` in customers has the same receipt key (`X-Request-Id`, `earn_points`). | A second sale with a reused id gets `reward_points_earned` of the first sale in its body, but the points are not added to the customer. Wrong data, but visible and limited to loyalty points. | code review | Not fixed: needs a step key per sale attempt instead of the client's id, a change in `common/` that also concerns variant A. Recorded as a limit in the report. |
| B3 | B | `common/db.py` opens a new MariaDB connection for every `transaction()`; there is no pool. A checkout with a customer opens four connections in till alone (checks, write, outbox read, outbox mark) plus one in customers and one in reporting. | Adds connection setup to every step and inflates checkout latency (C3). Same code in both variants, so the comparison stays fair, but the absolute numbers are worse than they need to be. | code review | Not fixed, on purpose: changing it in one variant would bias C3. Mentioned under limits in the report. |
| B4 | B | Calls between services use `httpx` with `timeout=2`; the gateway with `timeout=20`. | In `httpx` this is a limit per phase (connect, write, read, pool), not for the whole call. The design's "2 s per call" and the worst-case budget of 16 s behind the gateway's 20 s are therefore not hard limits. Low risk with small JSON answers. | code review | Not fixed (low risk, same in A). |
| B5 | B | `POST /internal/undo` answers `422` for an unknown step and `500` after three deadlocks. | The design says an undo always answers `200`. The agent listed this deviation itself under "Decisions taken by the agent". | code review of the agent's own notes | Accepted: only for programming errors or a failing database. |

# Comparison criteria

Group: F
Members: Karlis Kalnakarklis, Bozhidar Chobanov

## Criteria

All measured criteria are taken for both variants at `v1` and at `v2`, with
the monolith (`baseline`) as a point of comparison where the script supports
it.

| ID | Criterion | Which stakeholder cares, and why | Metric and unit | How it is measured | Weight | Hypothesis: A or B wins, because … |
|----|-----------|----------------------------------|-----------------|--------------------|--------|-------------------------------------|
| C1 | Checkout survives outages | Store manager: a till that stops causes a queue and costs customers. | Number of containers (services and data stores, not the gateway) whose stop makes checkout fail. Count, lower is better. | `make blast-a`, `make blast-b`: column `checkout` in `bench/results/<variant>-<level>-blast.json`. | 30% | **B**, because a capability-aligned selling service can keep the data it needs for checkout itself, while in A checkout calls people, stores and inventory and fails when any of them is down. |
| C2 | Spread of the change requests | Product Owner: VAT and loyalty are next on the roadmap. Head of Development: a change that touches fewer services needs fewer teams to agree. | Number of service folders changed from `v1` to `v2` (a shared folder such as `common/` counts as one). Count, lower is better. Lines added plus deleted as a tie-breaker. | `make impact`: `bench/results/change-impact.md`. | 25% | **B**, because VAT belongs to selling and loyalty to one capability, while in A each change crosses the table owners (VAT needs the product category from inventory; loyalty needs the sales history in sales and the points in people). |
| C3 | Checkout latency | Store manager: a slow till also makes the queue longer. | p95 latency of checkout through the gateway, in ms, lower is better. Hops per checkout reported alongside. | `make bench-a`, `make bench-b`: `use_cases.checkout.latency_ms.p95` and `hops` in `bench/results/<variant>-<level>-bench.json`. | 10% | **B**, because fewer synchronous calls per checkout are needed when the selling service has its own data; A makes six calls to other services per checkout. |
| C4 | Spread of personal data | Data Protection Officer: customer and employee personal data in as few places as possible. | Number of data stores that contain personal data of a customer or employee from the seed (name, email, phone, address, SSN). Count, lower is better. | `bench/personal_data.sh` (written after `v2`, run against both the `v1` and `v2` tags): dumps every data store of the running stack and searches it for the emails and last names of the customers and employees in `shared/seed.json`. | 15% | **A**, because one service (people) owns all personal data and the other services keep only IDs; B may keep copies of customer data where a capability needs them. |
| C5 | Reports reconcile | Head of Finance: end-of-day and sales reports must reconcile to the cent, every evening. | Level 1 to 3 on the scale below, higher is better. | Both members rate each variant on their own from `docs/design.md` and the code at `v1` and `v2`, then compare and agree on one level; differences and the reason are recorded in the report. | 20% | **A**, because in A one service (sales) owns all sales and returns and computes both reports from them; in B reporting may work on copies that are kept current later. |

Total weight: 100%.

## Scales for qualitative criteria

**C5: Reports reconcile**

The question for every level: can the Z-reports of a store for one day and
the sales report of that store for the same day disagree, and would anyone
see it?

| Level | Meaning |
|-------|---------|
| 1 | They can disagree in normal operation, without any failure or race, for example because a report reads copies that are updated later; or a mismatch cannot be found from the stored data. |
| 2 | They can disagree only through a specific, documented race (for example a sale in progress while its register is closed) or a documented failure (for example an undo that fails); a mismatch can be found from the stored data. |
| 3 | No order of requests and no failure of a single service can make them disagree. |

## Why these weights

We put the store manager first (C1 and C3 together 40%): a till that does not
work costs customers at once, every day, in every store, and it was the main
reason to split the monolith. Within that, availability (C1) weighs more than
speed (C3), because at a grocery till a few milliseconds go unnoticed while an
outage does not.

The spread of the change requests (C2, 25%) comes second: the roadmap is
known, and how well each cut absorbs change is what the decomposition is
meant to improve.

Reconciliation (C5, 20%) and personal data (C4, 15%) weigh less, not because
they matter less, but because both variants must meet them in any case; the
criteria only rate how easily.

Who would disagree: the Head of Finance would treat reconciliation as a hard
requirement, not a trade-off; the Data Protection Officer would say the same
about personal data, which is a legal duty; the Head of Development would
miss a criterion for team independence, which C2 covers only in part.

## Changes after `criteria-v1`

| Date | Change | Reason |
|------|--------|--------|
| 2026-11-03 | C4: `bench/personal_data.sh` is written after `v2` and run against both the `v1` and `v2` tags, instead of being written before `v1`. The metric, the search terms and the weight stay the same. | The script was not ready when we tagged `v1`, and we did not want to delay the `v1` measurements for it. Running it later against both tags measures exactly the same code, so the result is not affected; only the order of the work changed. |

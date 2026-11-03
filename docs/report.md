# Report

> About five pages. Every claim about a variant is backed by a measurement, a
> test result, a log excerpt or a reference to code. Delete the quoted
> guidance when you are done.

Group: F
Members: Karlis Kalnakarklis, Bozhidar Chobanov

## 1. Recommendation

> Three to five sentences for management: which decomposition, for which
> situation, and the most important price of that choice.

## 2. Results

All measurements were taken with `n = 30` requests per use case (3 warm-up)
through the gateway, on a fresh stack. Both variants pass all tests at both
versions: `make test-a` and `make test-b` (41 passed) at `v1`,
`make test-a-v2` and `make test-b-v2` (53 passed) at `v2`, and the
conformance checks (A: 43, B: 26 passed).

| ID | Criterion | Baseline | A `v1` | B `v1` | A `v2` | B `v2` | Evidence |
|----|-----------|----------|--------|--------|--------|--------|----------|
| C1 | Checkout survives outages: containers whose stop makes checkout fail (lower is better) | 1 of 1 | 8 of 8 | 4 of 8 | 8 of 8 | 4 of 8 | [`a-v1-blast.json`](../bench/results/a-v1-blast.json), [`b-v1-blast.json`](../bench/results/b-v1-blast.json), [`a-v2-blast.json`](../bench/results/a-v2-blast.json), [`b-v2-blast.json`](../bench/results/b-v2-blast.json), [`baseline-v1-blast.json`](../bench/results/baseline-v1-blast.json) |
| C2 | Spread of the change requests: service folders changed `v1` → `v2` (lines added + deleted) | – | – | – | 4 (200) | 4 (311) | [`change-impact.md`](../bench/results/change-impact.md) |
| C3 | Checkout latency: p95 in ms (hops) | 6.6 (0) | 36.7 (7) | 19.8 (3) | 31.9 (7) | 24.6 (3) | [`a-v1-bench.json`](../bench/results/a-v1-bench.json), [`b-v1-bench.json`](../bench/results/b-v1-bench.json), [`a-v2-bench.json`](../bench/results/a-v2-bench.json), [`b-v2-bench.json`](../bench/results/b-v2-bench.json), [`baseline-v1-bench.json`](../bench/results/baseline-v1-bench.json) |
| C4 | Spread of personal data: data stores with personal data (lower is better) | 1 of 1 | 1 of 4 | 1 of 4 | 1 of 4 | 1 of 4 | [`a-v1-personal.json`](../bench/results/a-v1-personal.json), [`b-v1-personal.json`](../bench/results/b-v1-personal.json), [`a-v2-personal.json`](../bench/results/a-v2-personal.json), [`b-v2-personal.json`](../bench/results/b-v2-personal.json), [`baseline-v1-personal.json`](../bench/results/baseline-v1-personal.json) |
| C5 | Reports reconcile: level 1 to 3 (higher is better) | | | | | | *to do: rating by both members* |

**C1 in detail.** In A, checkout fails when any one of the eight containers
is stopped, because sales calls stores, people and inventory on every
checkout. In B, checkout fails only when `till`, `customers` or one of their
databases is stopped; `purchasing` and `reporting` can be down. The measured
checkout has a customer ([`bench/usecases.py`](../bench/usecases.py)), so it
needs `customers` for the points. The other use cases at `v2`:

| Use case | A `v2`: fails when stopped | B `v2`: fails when stopped |
|----------|---------------------------|---------------------------|
| checkout, return | every container | till, customers (+ dbs) |
| Z-report | every container | till (+ db) |
| sales report | sales, stores (+ dbs) | reporting (+ db) |
| product lookup | inventory (+ db) | purchasing, till (+ dbs) |
| purchase order | inventory, people (+ dbs) | purchasing (+ db) |
| goods receipt | inventory, people (+ dbs) | purchasing, till (+ dbs) |

The blast results at `v2` are the same as at `v1` in both variants.

**C3 in detail.** A hop is one outgoing call in the call log, including the
gateway's call to the leader. A checkout in A is the gateway plus six calls
from sales; in B the gateway plus two calls from till (customers, reporting).
The change requests did not add a call to checkout in either variant. A
return gained one hop in both (A 4 → 5, B 2 → 3): the new step that takes
back points. The latency differences between `v1` and `v2` (A −4.8 ms,
B +4.8 ms) are within the noise of 30 requests; the hops are the more
stable measure.

**C4 in detail.** [`bench/personal_data.sh`](../bench/personal_data.sh)
dumps every data store of the running stack and searches it for the 23
emails and last names of the customers and employees in the seed. A last
name counts only as a whole stored value, so the vendor "Huber Handels GmbH"
does not count as the employee Huber. Each stack was started fresh and the
acceptance tests of that version were run first, so the stores also held
sales, returns and ledger entries; a fresh stack gave the same counts.

| Variant | Store with personal data | Search terms found | Tables |
|---------|--------------------------|--------------------|--------|
| Baseline | `legacy-db` | 23 of 23 | `customer_info`, `employee_info` |
| A (`v1`, `v2`) | `people-db` | 23 of 23 | `customer_info`, `employee_info` |
| B (`v1`, `v2`) | `customers-db` | 14 of 23 (customers only) | `customers` |

The count is the same, but the content differs. A keeps the legacy records
as they are, including the employees' SSN and the plain-text passwords
([`people/app.py`](../variant-a/people/app.py)). B keeps no personal data of
employees at all: till and purchasing know an employee only by
`staff_id` ([`till/app.py`](../variant-b/till/app.py),
[`purchasing/app.py`](../variant-b/purchasing/app.py)), and the customer
record has no password. No other store in B holds a copy of customer data,
not even reporting's ledger. The change requests added no personal data in
either variant.

## 3. How far the change requests spread

From [`change-impact.md`](../bench/results/change-impact.md) (tags `v1` →
`v2`):

| Variant A | Files | Added | Deleted | | Variant B | Files | Added | Deleted |
|-----------|-------|-------|---------|-|-----------|-------|-------|---------|
| sales | 1 | 142 | 21 | | till | 1 | 130 | 48 |
| people | 1 | 30 | 3 | | customers | 1 | 91 | 12 |
| inventory | 1 | 1 | 1 | | reporting | 1 | 24 | 1 |
| stores | 1 | 1 | 1 | | purchasing | 1 | 3 | 2 |
| **total: 4 folders** | 4 | 174 | 26 | | **total: 4 folders** | 4 | 248 | 63 |

In both variants the gateway, `common/` and `docker-compose.yml` did not
change, as the design predicted ([`design.md`](design.md), "Version 2: the
change requests"). No service, data store or network was added.

**Services per change request.** The numbers are the same in both variants:

| | Variant A | Variant B |
|---|---|---|
| CR1: Swiss VAT | inventory, sales, stores (3) | purchasing, till, reporting (3) |
| CR2: loyalty tiers | sales, people (2) | till, customers (2) |

In A, two of the four folders changed by one line each (inventory adds
`category` to its products answer, stores passes `vat` on into the
Z-report). The work is in sales, which owns sales, returns and both reports.
In B the work is split between till and customers, and reporting needs its
own VAT table.

**Interfaces between services that changed** (from the design and the
code):

- A: two new internal calls (people → sales for the spend and tier,
  sales → people to take back points) and two changed answers (products with
  `category`, session totals with `vat`). people now calls sales, which it
  did not do in `v1`.
- B: one new internal call (till → customers to take back points) and three
  changed ones (the price list with `category`, `earn` with `sale_date` and
  `tier`, the ledger entry with `vat`).

**Data that had to be added or migrated:**

- A, all in `sales-db`: three new tables (`vat_table`, `vat_category`,
  `ticket_vat`) and three new columns (`item_list.vat_rate`,
  `ticket_system.tier`, `ticket_system.points_rate`).
- B, in three stores: `till-db` two tables (`vat_rates`, `sale_vat`) and
  three columns (`price_list.category`, `sales.tier`,
  `sale_lines.vat_rate`); `customers-db` one table (`spend_entries`);
  `reporting-db` one table (`sale_entry_vat`).
- Both variants needed a migration for a database that `v1` created
  (findings A5 and B6 in [`findings.md`](../ai-log/findings.md)), which the
  agent left out at first. In B, the spend of sales made before the upgrade
  is not backfilled into `customers`; in A it is computed from sales' own
  tables, so nothing is missing.

**Why B changed more lines.** B keeps copies so that each capability can work
alone, and the change requests had to extend those copies too: the VAT per
rate is stored in till and again in reporting (the ledger), and customers
keeps its own spend record (`spend_entries`), fed by till, instead of reading
the sales history. In A the sales history and both reports are already in
one service, so the spend and the VAT sums are queries on tables sales owns.

The totals include the fixes of findings A5, B6 and B7 (commit `5cc93b3`):
35 lines in A and 92 lines in B. Without them A changed 165 lines and B 219.

**Preparation.** We did not prepare for the change requests in `v1` (see
[`design.md`](design.md), "Policy for the change requests"), so `v1` carried
no extra complexity, and these numbers show the full spread of each change.

## 4. Hypotheses and results

| ID | Hypothesis at `criteria-v1` | Result | Confirmed? |
|----|-----------------------------|--------|------------|
| C1 | B, because selling keeps the data it needs for checkout | B: 4 containers, A: 8, at `v1` and `v2` | Yes |
| C2 | B, because VAT belongs to selling and loyalty to one capability | Tie at 4 folders; A has fewer lines (200 against 311) | No |
| C3 | B, because fewer synchronous calls per checkout | B lower at both versions (19.8 / 24.6 ms against 36.7 / 31.9 ms; 3 hops against 7) | Yes |
| C4 | A, because people owns all personal data | Tie: 1 store in each variant, at `v1` and `v2` | No |
| C5 | A, because sales owns all sales and returns and computes both reports | *to do* | |

**C1.** As expected. In A, checkout calls three other services and needs all
four databases. The part we did not expect: in B, `customers` is also on the
checkout path, because a checkout with a customer adds the points
synchronously. Checkout without a customer in B depends only on till.

**C2.** The hypothesis was right about A: VAT needed the category from
inventory, and loyalty crossed sales and people. It was wrong about B: we
assumed VAT belongs only to selling, but in B the sales report lives in
reporting and the category in purchasing, so CR1 also crossed three
services. Loyalty in B touched two services, the same as in A. B also changed
more lines, because its copies (ledger, spend record) had to be extended as
well (see section 3).

**C3.** As expected. The hypothesis named six calls for A; the bench counts
seven hops, because it also counts the gateway's call to sales.

**C4.** The part about A was right: only people holds personal data. We
expected B to copy customer data where a capability needs it (for example
into the ledger), but it does not: till and reporting work with the customer
ID only, so B also has one store. B even holds less, because it keeps no
employee data at all, while A keeps the full legacy employee records. The
metric counts stores, not what they hold, so it does not show this
difference.

**C5.** Not rated yet.

**Changes after `criteria-v1`.** One change, recorded in
[`criteria.md`](criteria.md): the script for C4 (`bench/personal_data.sh`) is
written after `v2` and run against both tags, instead of being written
before `v1`. Reason: *to do*.

## 5. Decision and trade-offs

> What do you gain and what do you give up with your recommendation? Go
> through the stakeholders: whose concern is met, whose is not, and what you
> would tell them.

## 6. What would change the decision

> Concrete conditions (a number, a requirement, an organisational change)
> under which you would recommend the other variant.

## 7. What the DDD analysis showed

> Two or three findings from `domain.md` that matter for the decision.

## 8. Limits of this comparison

> What does your setup not show? Think of everything running on one machine,
> the size of the data, the number of stores and tills, the test-only reset.

## 9. Reflection on working with the coding agent

> Refer to `ai-log/findings.md`. Which kinds of mistakes did the agent make?
> Which of them did the tests catch, and which only your review or your
> measurements? Did the agent respect the variant rules? What would you
> specify differently next time? What did the agent do well?

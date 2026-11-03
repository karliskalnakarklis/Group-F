# Report

Group: F
Members: Karlis Kalnakarklis, Bozhidar Chobanov

## 1. Recommendation

We recommend variant B, the split by what the business does (selling, purchasing,
customers, reporting), for Frischwerk. The main reason is simple - in B the tills
keep selling when the back office or the reporting is down, and in A basically any
service that goes down stops every till. B is also faster at the till and keeps less
personal data (no employee records at all). The price is that B keeps some copies
of data (prices, the sales for the reports, the customer spend), so a change like the
loyalty programme costs more code (in our case about 50% more lines), and the sales
report can lag behind for a few seconds while reporting is down. If Frischwerk cares
more about cheap changes than about tills that keep running, A is the safer choice.

## 2. Results

All measurements were taken with `n = 30` requests per use case (3 warm-up)
through the gateway, on a fresh stack. Both variants pass all tests at both
versions: `make test-a` and `make test-b` (41 passed) at `v1`,
`make test-a-v2` and `make test-b-v2` (53 passed) at `v2`, and the
conformance checks (A: 43, B: 26 passed).

| ID | Criterion | Baseline | A `v1` | B `v1` | A `v2` | B `v2` | Evidence |
|----|-----------|----------|--------|--------|--------|--------|----------|
| C1 | Checkout survives outages: containers whose stop makes checkout fail (lower is better) | 1 of 1 | 8 of 8 | 4 of 8 | 8 of 8 | 4 of 8 | [`a-v1-blast.json`](../bench/results/a-v1-blast.json), [`b-v1-blast.json`](../bench/results/b-v1-blast.json), [`a-v2-blast.json`](../bench/results/a-v2-blast.json), [`b-v2-blast.json`](../bench/results/b-v2-blast.json), [`baseline-v1-blast.json`](../bench/results/baseline-v1-blast.json) |
| C2 | Spread of the change requests: service folders changed `v1` → `v2` (lines added + deleted) | *n/a: the monolith did not get the change requests* | *n/a: measured from `v1` to `v2`* | *n/a: measured from `v1` to `v2`* | 4 (200) | 4 (311) | [`change-impact.md`](../bench/results/change-impact.md) |
| C3 | Checkout latency: p95 in ms (hops) | 6.6 (0) | 36.7 (7) | 19.8 (3) | 31.9 (7) | 24.6 (3) | [`a-v1-bench.json`](../bench/results/a-v1-bench.json), [`b-v1-bench.json`](../bench/results/b-v1-bench.json), [`a-v2-bench.json`](../bench/results/a-v2-bench.json), [`b-v2-bench.json`](../bench/results/b-v2-bench.json), [`baseline-v1-bench.json`](../bench/results/baseline-v1-bench.json) |
| C4 | Spread of personal data: data stores with personal data (lower is better) | 1 of 1 | 1 of 4 | 1 of 4 | 1 of 4 | 1 of 4 | [`a-v1-personal.json`](../bench/results/a-v1-personal.json), [`b-v1-personal.json`](../bench/results/b-v1-personal.json), [`a-v2-personal.json`](../bench/results/a-v2-personal.json), [`b-v2-personal.json`](../bench/results/b-v2-personal.json), [`baseline-v1-personal.json`](../bench/results/baseline-v1-personal.json) |
| C5 | Reports reconcile: level 1 to 3 (higher is better) | *not rated: C5 rates the two variants* | 2 | 2 | 2 | 2 | Rating by both members, see "C5 in detail" below; [`design.md`](design.md), [`stores/app.py`](../variant-a/stores/app.py), [`till/app.py`](../variant-b/till/app.py) |

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

**C5 in detail.** Each member rates both variants on their own, from
[`design.md`](design.md) and the code, on the scale in
[`criteria.md`](criteria.md); then we agree on one level.

| Variant | Karlis `v1` | Karlis `v2` | Bozhidar `v1` | Bozhidar `v2` | Agreed `v1` | Agreed `v2` |
|---------|-------------|-------------|---------------|---------------|-------------|-------------|
| A | 2 | 2 | 2             | 2             | 2           | 2           |
| B | 2 | 2 | 2             | 2             | 2           | 2           |

*Karlis's reasons:*

- **A, level 2.** Both reports are computed in sales from the same tables,
  so they cannot drift apart in normal operation. They can disagree through
  one documented race: a sale or return that checked "session open" just
  before the close and commits after stores has read the totals is missing
  from the Z-report, but counts in the sales report
  ([`design.md`](design.md), variant A "Failure behaviour"). It can also
  happen through a documented failure: if the call for the totals fails and
  the session cannot be reopened (finding A4). Both can be found from the
  stored data: the sale is stored with a session whose `close_time` is
  before the sale.
- **B, level 2.** The Z-report is computed in till, with the shift row
  locked, so A's race cannot happen. The sales report reads reporting's
  copies, but till delivers each entry in the same request, before it
  answers `201` ([`till/app.py`](../variant-b/till/app.py), `deliver` right
  after the commit). So in normal operation the copy is already there. The
  reports can disagree only in the milliseconds between till's commit and
  the delivery, or while reporting is down or slow; then the entries wait in
  till's outbox and are sent within seconds. Every missing entry is visible
  as an undelivered row in `ledger_outbox`. A delivery twice changes nothing
  (fixed before `v1`, finding B1).
- **Not level 3 for either**, because one failure (sales in A, reporting in
  B) or one order of requests (A) can make the reports disagree.
- **`v2` does not change the level.** In both variants the VAT per rate is
  stored once per sale and both reports add up the stored values: in A from
  `ticket_vat`, in B from `sale_vat` in till and its copy in reporting.
- **Same in both, not counted:** a shift that runs over midnight has its
  sales split over two days in the sales report but not in the Z-report.
  This comes from the contract, not from the cut.

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
| C5 | A, because sales owns all sales and returns and computes both reports | Tie: level 2 in both variants, at `v1` and `v2` | No |

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

**C5.** Both variants are at level 2, at `v1` and `v2` (section 2). The
part about A was right: sales computes both reports from its own tables, so
they cannot drift apart in normal operation. But A splits the close of a
register between stores and sales, so a sale in progress at the close can be
missing from the Z-report. We expected B's reports to drift apart because
reporting works on copies; but till delivers each copy before it answers, so
the copies lag only while reporting is down, and B's close has no race. Each
variant has one documented way to disagree, and both can be found from the
stored data.

**Changes after `criteria-v1`.** One change, recorded in
[`criteria.md`](criteria.md): the script for C4 (`bench/personal_data.sh`) is
written after `v2` and run against both tags, instead of being written
before `v1`. Reason: *to do*.

## 5. Decision and trade-offs

**We recommend variant B (capability-aligned).** Adding up the weights from
[`criteria.md`](criteria.md), where the winner of a criterion gets its full
weight and a tie splits it, B scores 57.5 and A 42.5:

| ID | Weight | Winner | A | B |
|----|--------|--------|---|---|
| C1 Checkout survives outages | 30% | B | 0 | 30 |
| C2 Spread of the change requests | 25% | A (on lines only) | 25 | 0 |
| C3 Checkout latency | 10% | B | 0 | 10 |
| C4 Spread of personal data | 15% | tie | 7.5 | 7.5 |
| C5 Reports reconcile | 20% | tie | 10 | 10 |
| **Total** | 100% | | **42.5** | **57.5** |

**Stakeholders: whose concern is met, and what we would tell them.**

| Stakeholder | Concern | Met with B? | What we would tell them |
|-------------|---------|-------------|-------------------------|
| Store manager | Checkout keeps working when other parts are down | **Yes** | Checkout needs only till and customers (4 of 8 containers, against 8 of 8 in A). Back office and reporting can be down, and the tills keep selling. If customers is down, a sale without the loyalty card still works. |
| Store manager | A fast till | **Yes** | 3 hops per checkout against 7 in A (p95 24.6 ms against 31.9 ms at `v2`). |
| Head of Finance | Reports reconcile to the cent | **Partly**, same as A | Both variants are at level 2. In B the Z-report cannot miss a sale, but the sales report lags while reporting is down; every missing entry is visible in till's outbox and is sent within seconds once reporting is back. |
| Data Protection Officer | Personal data in as few places as possible | **Yes**, same count as A | One store holds personal data, as in A, and B holds less: no employee records, no SSNs, no passwords. |
| Product Owner | VAT and loyalty are easy to add | **Partly** | Both changes touched 4 services in both variants, but B needed about 50% more lines (311 against 200), because its copies (ledger, spend record, price list) had to be extended too. Expect each change that touches sales data to cost more code in B. |
| Head of Development | Teams deploy without waiting for each other; not too many services | **Mostly** | 4 services and 4 databases, the same as A. Till is the centre: customers and purchasing are upstream of it, reporting downstream. The one two-way dependency, purchasing ↔ till on goods receipt, still needs both teams to agree ([`domain.md`](domain.md)). |

**What we gain:** the tills keep selling through most outages, checkout is
faster, the rules the store manager and the Head of Finance care about are
checked in one service (till), and B keeps less personal data.

**What we give up:** copies. B keeps a price list, a ledger and a spend
record that are filled from other services. This made the change requests
cost more code, the price can be up to 60 s old at the till, and the sales
report lags during a reporting outage.

## 6. What would change the decision

We would recommend variant A under any of these conditions:

| Condition | Why it would favour A |
|-----------|-----------------------|
| **Outages weigh less than change.** For example, the tills get an offline mode, so C1 drops to 20% and C2 rises to 35%. | B's lead comes from C1. With these weights A scores 52.5 and B 47.5. |
| **Many more changes like CR2 are planned** that touch the sales history and the reports. | Every such change must also extend B's copies; in our change requests that cost B about 50% more lines (311 against 200). |
| **A price change must apply at every till at once.** | B's till sells with a copy of the price list that can be up to 60 s old. A reads the price from inventory on every sale. |
| **The sales report must be correct even during an outage**, with no lag at all. | B's sales report lags while reporting is down. A's reports come from sales, the same service as the sales themselves. A would still need to close its race at the close of a register to reach level 3. |
| **All services run on one host** that fails as a whole. | When all containers stop together, B's advantage in C1 disappears, and A's single source for every fact is simpler. |

## 7. What the DDD analysis showed

The full analysis is in [`domain.md`](domain.md). Three findings matter for
the decision.

**1. A cuts three rules in half; B keeps them inside till.** In A, the open
shift, the Z-report and the loyalty rule each need two services: stores and
sales for the first two, sales and people for loyalty. Each of them costs a
call between services and either an undo or an accepted race. In B, the
shift, the Z-report, stock and gift cards are checked in one transaction in
till; the only rule B splits is the goods receipt (purchasing and till),
which is back office ([`domain.md`](domain.md), "Aggregates and
invariants"). This explains the measurements: six calls per checkout in A
against two in B (C3), and 8 containers that stop checkout in A against 4 in
B (C1). It also matters for C5, because the Z-report is one of the rules A
splits.

**2. A is one legacy model cut by foreign keys, not a set of bounded
contexts.** A keeps the legacy names in every service, has no translation
layer, and its context map has two cycles: stores ↔ sales, and since CR2
people ↔ sales. B's map is almost a tree with till in the middle
([`domain.md`](domain.md), "Context map"). CR2 showed this in practice: in A
the loyalty rule had to go into sales, because the spend is computed from
sales' tables, while the points stay in people. In B the rule changed only in
customers; till got one new call and stores the tier it is given. `make
impact` counts both as two services (section 3), so the metric does not show
the new cycle in A.

**3. Personal data: the subdomains explain the C4 result.** Staff records are
a generic subdomain that the PoS needs only as an ID. A puts them together
with the loyalty customers in people, so every till use case depends on
people, and the employees' SSNs and passwords stay in the PoS. B keeps
employees as `staff_id` only. Both variants keep personal data in one store
(C4), but B keeps less of it.

**What the analysis changed.** We did not refine variant B in the code:
`v1` and `v2` were already built and measured, and a new cut would have made
the measurements compare something else than what we designed. The weakest
spot the analysis found in B is the two-way dependency between purchasing
and till on goods receipt, which works against the Head of Development's wish
that teams deploy without waiting for each other. The refinement we would
make is described in [`domain.md`](domain.md), "What the analysis changed".

## 8. Limits of this comparison

| Limit | What it means for our results |
|-------|-------------------------------|
| Everything runs on one machine | Calls between services never cross a real network, so a hop costs much less than in production. The latency gap between A (7 hops) and B (3 hops) would likely be larger (C3). |
| Small data | The seed has 7 customers, 6 employees and a few products. Reports and the 365-day spend never get slow, so the cost of A's extra calls and B's copies is not visible at scale. |
| Few stores and tills, one client | No load from many tills at once. The races we know of (a sale while its register closes, two checkouts of the last item) were never triggered, which matters for C5. |
| The reset before every run | Every `make up` starts from the seed. A real upgrade from `v1` to `v2` on existing data was never measured, and the missing migrations (findings A5, B6) were found only by code review. |
| 30 requests per measurement | Latency differences of a few milliseconds, such as between `v1` and `v2`, are noise. The hops are the more reliable number. |
| One container stopped at a time | The blast test does not show two failures at once, or a service that is slow but still answers (C1). |
| C4 searches emails and last names only | Phone numbers, addresses and SSNs are not counted. They are in the same tables, so the count does not change, but the metric does not show how much is stored (section 2). |
| The code is written by an agent | The results reflect our design, but also how the agent filled the gaps (see `ai-log/findings.md`). Another implementation of the same cut could measure differently. |

## 9. Reflection on working with the coding agent

I drove the agent for version 2, and Karlis did version 1.
All the mistakes we found are in [`findings.md`](../ai-log/findings.md), and how we
used AI outside of the code is in [`other.md`](../ai-log/other.md).

**What kind of mistakes it made.** Honestly, the code itself was rarely "wrong" in
the normal sense. Most of the time the agent did exactly what our design said, also
when the design was wrong. A1, B1 and B2 are the best example - we keyed the undo
receipts on the request id that the client chooses, and the agent implemented it
word for word without asking, even though AGENTS.md tells it to ask when something is
open. The second kind is things it simply left out because nobody asked: the
migrations from v1 to v2 (A5, B6). And the third kind surprised me and Karlis the most. In B7 it
kept fewer changed lines (which looks better in `make impact`) and in exchange a slow
customers service could block till's database connections. So it was kind of
optimising for our measurement,but for sure not for the store.

**What the tests caught.** None of these. Every finding came from reading the code
against the design and from our own small tests by hand (sending the same request
twice, upgrading v1 to v2 without wiping the database, pausing customers). The tests
were green the whole time, and the agent always reported "41 passed" or "53 passed"
like that means it is done. That was the biggest lesson from the tests -> that basically green tests only
mean the contract works on a fresh database, and not that the design is right.

**Did it respect the variant rules?** Yes. Conformance passed in both variants, A kept
the legacy tables and names, B used the business names from our language table, and
it did not add extra services. When the design left something open, it mostly wrote
it down under "Decisions taken by the agent", which made the review for us a lot easier.

**What I would specify differently next time.**

- Ask the agent to list the open questions and the risky spots first, before it
  writes any code (for example "who chooses this id?", "what happens to an existing
  database?" and etc...).
- Write the upgrade from v1 to v2 into the design as a requirement, and not assume it.
- Say clearly that the number of changed lines does not matter, so it does not try to
  make the diff look small.
- Keep the prompts shorter and do one variant per session, so the logs are easier to
  follow.
- Keep better track of the AI log.

**What it did well.** It was fast and consistent. Version 1 of both variants passed
all acceptance tests on the first run, the code looked the same in every service, and
it kept the docs and the code in sync when we asked for a fix. It also saved us a lot
of time on the more "boring" parts (compose files, schemas, the call log) which required redundant work. But in the end 
I would compare to like reviewing the code of a very quick colleague who never asks questions - you
still have to read everything yourself, and the design decisions stay on you.

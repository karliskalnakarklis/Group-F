# Design

> This is the specification you give the coding agent, one section per
> variant. Be precise: what you leave open, the agent decides for you.
> The rules of each variant are in `variant-a/README.md` and
> `variant-b/README.md`; the external behaviour is in `contract.md`.
> Delete the quoted guidance when you are done.

## Decisions common to both variants

> For example: technology per service, how services talk to each other
> (HTTP, messages), how a request that spans services stays all-or-nothing,
> how the call log is written, how the seed data is loaded.

| Decision | Choice | Reason |
|----------|--------|--------|
| Technology | Python 3.12 with FastAPI in every service. One MariaDB 11.4 container per service that owns data. | Same as the monolith. The same stack in both variants keeps the comparison fair. |
| How services talk | Synchronous HTTP with JSON. No message broker. | The tests read the result right after a write, so every change must be done when the request returns. Fewer containers. |
| All-or-nothing | The service that owns the main record of a use case leads it. It does all reads and checks first, then the writes in other services, then its own write last. If a step fails, it undoes the earlier writes in reverse order. A service that does not answer within 2 s counts as failed (`503`). | Without one shared database, this is the simplest way to leave nothing half done. The leader's own write comes last because it is the least likely to fail. |
| Call log | Shared code in `common/` in the variant folder. It logs every incoming request and outgoing call to `/logs/<service>.jsonl` and passes `X-Request-Id` on. | One implementation, the same in every service. |
| Seed data | Each service reads `/shared/seed.json` at start and loads only its own data. | Contract. No seed data in the code. |

### Policy for the change requests

> Do you prepare the design for CR1 and CR2 before `v1`? What exactly, and
> why? The same policy applies to both variants.

We do **not** prepare for CR1 and CR2 in v1. Version 1 implements only the
contract as it is: no extra tables, columns, fields or endpoints for VAT or
loyalty tiers.

Reason: we want `make impact` to show how far each cut lets a change spread.
Preparing would hide that and make v1 more complex. The service cuts were
chosen knowing the roadmap; that cannot be avoided and is the same for both
variants.

---

## Variant A: data-aligned

### Services

| Service | Responsibility | Owns (legacy tables) | Store |
|---------|----------------|----------------------|-------|
| gateway | routing, composition | none | none |
| people | customers and employees | `customer_info`, `employee_info` | `people-db` |
| stores | stores, registers, register sessions, Z-report | `stores`, `store_registers`, `registers_table` | `stores-db` |
| inventory | products, stock, vendors, purchase orders | `product_inventory`, `vendorinfo`, `orders_ticket`, `orders` | `inventory-db` |
| sales | sales, returns, gift cards, tax rate, sales report | `ticket_system`, `cart_inprogress`, `item_list`, `ticket_gift_payment`, `return_table`, `return_items`, `gift_card`, `tax_table` | `sales-db` |

### Components

```mermaid
flowchart LR
    client[Client] --> gw[gateway]
    gw --> people & stores & inventory & sales
    sales --> stores & people & inventory
    stores --> people & sales
    inventory --> people
    people --> pdb[(people-db)]
    stores --> sdb[(stores-db)]
    inventory --> idb[(inventory-db)]
    sales --> sadb[(sales-db)]
```

### Use case flows

> For each use case: which services take part, in which order, synchronous
> or asynchronous. At least checkout and the Z-report as sequence diagrams.

```mermaid
sequenceDiagram
    participant C as Client
    participant G as gateway
    participant S as sales
    participant ST as stores
    participant P as people
    participant I as inventory
    C->>G: POST /sales
    G->>S: POST /sales
    S->>ST: open session of the register?
    S->>P: employee exists?
    S->>P: customer exists? (if customer)
    S->>I: price, cost and stock of the products
    Note over S: compute totals with tax_table,<br/>check payments and gift card balances
    S->>I: take stock
    S->>P: add points (if customer)
    Note over S: one transaction: ticket, cart, lines,<br/>gift card debit (checked again), payments
    S-->>G: 201 sale
    G-->>C: 201 sale
```

```mermaid
sequenceDiagram
    participant C as Client
    participant G as gateway
    participant ST as stores
    participant P as people
    participant S as sales
    C->>G: POST /registers/{r}/close
    G->>ST: POST /registers/{r}/close
    ST->>P: employee exists?
    Note over ST: lock the open session
    ST->>S: totals of the session
    Note over ST: compute cash_expected and difference,<br/>close the session
    ST-->>G: 200 Z-report
    G-->>C: 200 Z-report
```

### All-or-nothing

> A failed request changes nothing (contract). How do you guarantee this when
> a sale touches stock, gift cards and points in different services?

We follow the shared rule: checks first, then the writes in other services,
then the leader's own transaction. If a step fails, the earlier writes are
undone in reverse order.

- **Checkout:** sales takes stock (inventory), then adds points (people), then
  writes the sale in its own transaction. If adding points fails, sales gives
  the stock back. If its own transaction fails, sales takes the points back
  and then gives the stock back.
- **Gift cards:** they belong to sales, so the debit is part of the sale's own
  transaction. The balance is checked again there under a row lock, so it
  never goes below zero.
- **Return:** sales adds the stock back (inventory), then writes the return.
  If its own transaction fails, sales takes the stock again.
- **Goods receipt:** stock and order status are both in inventory, so one
  transaction is enough.

### Failure behaviour

| What fails | What happens | Why this is acceptable or not |
|------------|--------------|-------------------------------|
| people | No sale, return, register open or close, purchase order or receipt (the employee check fails). Customer endpoints fail. | Not acceptable for the store manager: every till stops. This is the cost of one owner per table and no copies. |
| stores | No sale, return, register open or close, or sales report. | Not acceptable for the store manager: sales cannot check the register session. |
| inventory | No sale, return, product lookup, purchase order or receipt. | Expected: every sale needs prices and stock. |
| sales | No sale, return, gift card, sales report or Z-report. | Expected: sales is the core of the till. |
| an undo fails | Data stays half done, for example stock taken without a sale. The service logs an error. | Known gap, accepted for this assignment. Rare, because the leader's own transaction comes last. |

---

## Variant B: capability-aligned

### Services

| Service | Capability | Owns (its own model) | Copies of data from others (source, how kept current) | Store |
|---------|------------|----------------------|--------------------------------------------------------|-------|
| gateway | routing, composition | none | none | none |
| | | | | |

### Components

```mermaid
flowchart LR
    client[Client] --> gw[gateway]
```

### Use case flows

```mermaid
sequenceDiagram
    participant C as Client
    participant G as gateway
    C->>G: POST /sales
    G-->>C: 201 sale
```

### Language

| Legacy name | Name in this variant | Service |
|-------------|----------------------|---------|
| ticket_system | | |
| | | |

### All-or-nothing

### Failure behaviour

| What fails | What happens | Why this is acceptable or not |
|------------|--------------|-------------------------------|
| | | |

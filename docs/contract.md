# Contract

This is the external behaviour of the Frischwerk point-of-sale (PoS) system.
The monolith in `baseline/` and **both** of your variants must show it. The
acceptance tests in `tests/acceptance/` check this contract through the
gateway, and nothing else. How the system is decomposed behind the gateway is
your design, within the rules of the variant
([`variant-a/README.md`](../variant-a/README.md),
[`variant-b/README.md`](../variant-b/README.md)).

The change requests in [`change-requests.md`](change-requests.md) change parts
of this contract for version 2.

Do not change this file, `shared/` or anything in `tests/`.

## Stack

| Rule | |
|---|---|
| Entry point | One service named `gateway`, published on host port **8000**. It is the only service with a published port. |
| Compose | `name: pos` in every compose file. Only one stack runs at a time. |
| Health | Every service answers `GET /health` with `200`. |
| Seed data | Every stack starts from [`shared/seed.json`](../shared/seed.json): one key per legacy table, with the legacy column names. `make up-…` deletes all data and starts from the seed again. |
| Data stores | Every database container is described in [Data ownership](#data-ownership). A service may also keep its data inside its own container (for example SQLite); such a service needs no store label. |

## Conventions

- Request and response bodies are JSON. Amounts are in CHF, as numbers with
  two decimals, rounded half up to 0.01 at each step named below.
- IDs are integers. Dates are `YYYY-MM-DD` in Europe/Zurich.
- An error is a JSON body `{ "detail": "<text>" }` with the status code and a
  keyword from [Errors](#errors) in the text. The tests break one rule at a
  time.
- A request that fails changes nothing: no stock, balance, points, sale or
  return is left behind half done.

## Endpoints

### Catalogue and customers

| Method and path | Request | Success |
|---|---|---|
| `GET /products/{id}` | | `200` `{ product_id, name, brand, category, unit_price, cost, in_stock, vendor_id }` |
| `POST /customers` | `{ first_name, last_name, email, phone, street, zip_code, city }` | `201` `{ customer_id, ... }` |
| `GET /customers/{id}` | | `200` `{ customer_id, first_name, last_name, email, reward_points }` |
| `POST /gift-cards` | `{ amount }` | `201` `{ gift_card_id, balance }` |
| `GET /gift-cards/{id}` | | `200` `{ gift_card_id, balance }` |

`category` is the legacy `productType`, `name` is `productName`. A new
customer has `reward_points` `0`.

### Registers

A register (`register_num` in the seed) belongs to a store. Sales and returns
need an **open register session**.

| Method and path | Request | Success |
|---|---|---|
| `POST /registers/{register}/open` | `{ employee_id, opening_cash }` | `201` `{ session_id, register, opened_at }` |
| `POST /registers/{register}/close` | `{ employee_id, counted_cash }` | `200` Z-report, see below |

The **Z-report** covers the sales and returns of the session that is closed:

```json
{
  "session_id": 7, "register": 2,
  "sales_count": 3, "gross_total": 104.35, "tax_total": 7.73,
  "refunds_total": 9.70, "cash_sales": 54.10,
  "opening_cash": 200.00, "cash_expected": 244.40,
  "counted_cash": 244.40, "difference": 0.00
}
```

- `gross_total`, `tax_total`: sums of `total` and `tax` of the session's sales.
- `refunds_total`: sum of the `refund_amount` of the session's returns.
- `cash_sales`: sum of the session's cash payments.
- `cash_expected = opening_cash + cash_sales - refunds_total` (refunds are
  paid in cash).
- `difference = counted_cash - cash_expected`.

### Sales (checkout)

`POST /sales`

```json
{
  "register": 1, "employee_id": 2, "customer_id": 4,
  "lines": [ { "product_id": 5, "qty": 2 }, { "product_id": 40, "qty": 1 } ],
  "payments": [ { "method": "gift_card", "gift_card_id": 3, "amount": 10.00 },
                { "method": "cash", "amount": 9.99 } ]
}
```

`customer_id` is optional. `method` is `cash`, `card` or `gift_card`.

`201`:

```json
{
  "sale_id": 12, "register": 1, "date": "2026-10-05", "customer_id": 4,
  "lines": [ { "product_id": 5, "qty": 2, "unit_price": 4.99, "line_total": 9.98 }, ... ],
  "subtotal": 18.48, "tax": 1.48, "total": 19.96,
  "reward_points_earned": 19,
  "payments": [ ... ]
}
```

Rules (version 1):

- `unit_price` is the product's `unit_price` at the time of the sale (net).
  `line_total = qty × unit_price`; `subtotal` = sum of line totals.
- `tax = subtotal × tax_rate`, where `tax_rate` is from the row of
  `tax_table` with the latest `tax_year`. `total = subtotal + tax`.
- Every line needs enough stock; the sale reduces the stock of every line.
- The payments add up to exactly `total`. A gift card payment reduces the
  card's balance; the balance never goes below zero. Several payments with
  the same card count together.
- With a customer, the customer earns `floor(total)` reward points.

`GET /sales/{id}` returns the same body as the `201`.

### Returns

`POST /returns`

```json
{ "sale_id": 12, "register": 1, "employee_id": 2,
  "lines": [ { "product_id": 5, "qty": 1 } ] }
```

`201` `{ return_id, sale_id, lines: [ { product_id, qty } ], refund_amount }`

- Only products of that sale can be returned, and in total at most the
  quantity sold; several returns of one sale are allowed up to that limit.
- `refund_amount` = sum over the lines of `qty × unit_price` from the sale,
  plus tax at the sale's rate. The refund is paid in cash.
- Returned items go back into stock. Reward points are not changed
  (version 1).

### Purchasing

| Method and path | Request | Success |
|---|---|---|
| `POST /purchase-orders` | `{ vendor_id, employee_id, lines: [ { product_id, qty } ] }` | `201` `{ purchase_order_id, vendor_id, status: "open", lines, total_cost }` |
| `GET /purchase-orders/{id}` | | `200` same body |
| `POST /purchase-orders/{id}/receipt` | `{ employee_id }` | `200` same body with `status: "received"` |

- Every product of an order must be supplied by that vendor.
- `total_cost` = sum of `qty × cost`.
- The goods receipt adds the ordered quantities to the stock. An order is
  received once.

### Sales report

`GET /reports/sales?store={SID}&from={date}&to={date}` (both dates inclusive)

```json
{
  "store": 1, "from": "2026-10-01", "to": "2026-10-31",
  "sales_count": 120, "gross_total": 5400.10, "tax_total": 400.01,
  "refunds_total": 35.50, "net_revenue": 5364.60,
  "top_products": [ { "product_id": 5, "qty": 64 }, ... ]
}
```

- A sale belongs to the store of its register, a return to the store of its
  register.
- `net_revenue = gross_total - refunds_total`.
- `top_products`: at most five products with the highest quantity sold (not
  reduced by returns), highest first.

## Errors

| Situation | Status | Keyword in `detail` |
|---|---|---|
| Unknown product, customer, employee, vendor, gift card, sale, register, store or purchase order | 404 | `not found` |
| Not enough stock for a line | 409 | `stock` |
| Register not open (sale, return), already open (open) or not open (close) | 409 | `register` |
| Payments do not add up to the total | 422 | `payment` |
| Gift card balance too low | 409 | `gift card` |
| Product not in the sale, or more returned than sold | 409 | `return` |
| Product not supplied by the order's vendor | 422 | `vendor` |
| Purchase order already received | 409 | `received` |
| Malformed request (missing fields, `qty` < 1, empty `lines`) | 422 | none required |

## Call log

Every service, including the gateway, makes its calls visible so that the
number of hops per request can be counted for any decomposition.

- The gateway takes the `X-Request-Id` header of the client, or creates one,
  and every service passes it on with every call it makes (as a header, or in
  the metadata of a message).
- Every service appends one JSON line to `/logs/<service>.jsonl` for every
  request it receives (`"direction": "in"`) and every call or message it sends
  (`"direction": "out"`):

  ```json
  {"time": "2026-10-05T10:15:02.123+02:00", "service": "gateway", "request_id": "3f2a...",
   "direction": "out", "method": "POST", "target": "sales", "path": "/sales",
   "status": 201, "duration_ms": 12.4}
  ```

  `target` is the compose service name of the receiver (or the topic for a
  message). `/logs` is the compose volume `calllogs`, mounted into every
  service.

## Data ownership

Every database container, and in variant A every application service, carries labels:

| Label | Value |
|---|---|
| `pos.role` | `store` for a database container (a message broker may use `broker`; it is not a store) |
| `pos.owner` | for a `store`: the one service that may use it |
| `pos.tables` | variant A only, on application services: the legacy tables the service owns, comma-separated |

A store shares a network only with its owner. Besides the gateway there are
at least three application services, and the gateway owns no store.
`make conformance-a` and `make conformance-b` check these rules from the
compose file.

# Change requests for version 2

Both change requests are known from the start. Implement them **after** you
have tagged `v1`, in both variants (see [`assignment.md`](assignment.md)).
Everything in the [contract](contract.md) that is not changed here stays as it
is. The tests are in `tests/cr/`; `make test-a-v2` and `make test-b-v2` run
them together with the acceptance tests in their version 2 form.

## CR1: Swiss VAT

> **Head of Finance:** "We are a Swiss company with a US tax table. From now
> on our prices include VAT, and receipts and reports show VAT per rate."

1. `unit_price` is a **gross** price that includes VAT.
2. VAT rates by product category (`category` = legacy `productType`):

   | Rate | Categories |
   |---|---|
   | 2.6% (reduced) | Dairy, Produce, Beef, Poultry, Pasta, DryGoods, PetFood |
   | 8.1% (standard) | every other category, for example Bathroom |

3. Sale: `line_total = qty × unit_price`; `total` = sum of line totals.
   For each rate: `gross` = sum of the line totals at that rate,
   `vat = gross × rate / (1 + rate)` rounded to 0.01, `net = gross - vat`.
   `tax` = sum of the `vat` values, `subtotal = total - tax`.
   The sale has a new field:

   ```json
   "vat": [ { "rate": 0.026, "net": 9.73, "vat": 0.25, "gross": 9.98 },
            { "rate": 0.081, "net": 17.57, "vat": 1.42, "gross": 18.99 } ]
   ```

   Only rates that occur in the sale are listed, lowest rate first.
4. Return: `refund_amount` = sum of `qty × unit_price` from the sale (gross).
5. The Z-report and the sales report get the same `vat` field, summed over
   their sales (not reduced by returns). `tax_total` = sum of the `vat`
   values.
6. `tax_table` is no longer used. In variant A it keeps its owner.

## CR2: Loyalty tiers

> **Product Owner:** "Customers who shop with us more should earn more. And a
> return must take back the points it earned."

1. A customer's **spend** is the sum of the `total` of the customer's sales in
   the last 365 days (today and the 364 days before), minus the
   `refund_amount` of all returns of those sales.
2. Tier, determined **before** a sale from the spend so far:

   | Tier | Spend (CHF) | Points per full CHF of the sale's `total` |
   |---|---|---|
   | `bronze` | below 500 | 1 |
   | `silver` | 500 to below 2000 | 2 |
   | `gold` | 2000 and more | 3 |

   `reward_points_earned = floor(total) × points per CHF`. The sale has a new
   field `tier`: the tier that applied, or `null` for a sale without a
   customer.
3. A return reduces the customer's points by
   `floor(refund_amount) × points per CHF of the original sale`. Points never
   go below 0.
4. `GET /customers/{id}` returns two new fields: `tier` and `spend_12m`.

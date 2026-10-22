# Variant A: data-aligned

The services follow the legacy data.

## Rules

1. Besides the `gateway`, there are at least three application services.
2. Each service owns a cluster of legacy tables that belong together. Every
   table in the list below has **exactly one** owning service, declared in the
   compose file with the label `pos.tables` (see the contract, "Data
   ownership"):

   `customer_info`, `employee_info`, `stores`, `store_registers`,
   `vendorinfo`, `product_inventory`, `gift_card`, `tax_table`,
   `registers_table`, `ticket_system`, `cart_inprogress`, `item_list`,
   `ticket_gift_payment`, `return_table`, `return_items`, `orders_ticket`,
   `orders`

   Tables or columns that you add (for example for the change requests)
   follow the legacy style and belong to one service; they do not need to be
   declared.

3. One source for every fact: a service does not keep a copy of data from
   another service's tables. It asks the owner when it needs the data. IDs,
   and values that are part of a transaction (for example the price at the time
   of a sale, or the register a sale was made at), are not copies.
4. Inside a service, the legacy table and column names stay. How the services
   name things in their APIs to each other is your choice; the gateway speaks
   the contract.
5. The `gateway` routes requests and composes answers. It owns no business
   data.

## What you put in this folder

- `docker-compose.yml` that starts the variant with `make up-a`
- one folder per service with its code and its `Dockerfile`

Follow the conventions in [`AGENTS.md`](../AGENTS.md).

## Checked by

`make conformance-a`: the stack rules, the data-ownership rules, and that
every legacy table above has exactly one owner.

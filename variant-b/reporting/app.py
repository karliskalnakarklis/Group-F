"""reporting (variant B): sales reporting for head office and finance.
Keeps the sales ledger (sale entries with their lines, refund entries) in
reporting-db. The entries come from till's outbox (docs/design.md, "Ledger
delivery to reporting")."""
import datetime as dt
from datetime import date

from fastapi import Query
from pydantic import BaseModel, Field

from common.calllog import create_app
from common.db import (APPLIED_STEPS, finish_step, init_database, install_undo, money, one, require, start_step,
                       transaction)

APP = create_app("reporting")

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
  store_id int NOT NULL PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS sale_entries (
  sale_id int NOT NULL PRIMARY KEY, store_id int NOT NULL, sold_on date NOT NULL,
  total decimal(12,2) NOT NULL, tax decimal(12,2) NOT NULL,
  KEY store_day (store_id, sold_on)
);
CREATE TABLE IF NOT EXISTS sale_entry_lines (
  sale_id int NOT NULL, line_no int NOT NULL, product_id int NOT NULL, qty int NOT NULL,
  PRIMARY KEY (sale_id, line_no)
);
CREATE TABLE IF NOT EXISTS refund_entries (
  return_id int NOT NULL PRIMARY KEY, sale_id int NOT NULL, store_id int NOT NULL, refunded_on date NOT NULL,
  refund_amount decimal(12,2) NOT NULL,
  KEY store_day (store_id, refunded_on)
);
""" + APPLIED_STEPS


def fill(cur, seed: dict) -> None:
    """The store list (legacy stores.SID); names and managers are not needed here."""
    for s in seed["stores"]:
        cur.execute("INSERT INTO stores (store_id) VALUES (%s)", (s["SID"],))


@APP.on_event("startup")
def startup():
    init_database(SCHEMA, fill, "stores")


# --- ledger entries (from till) ----------------------------------------------------

class EntryLine(BaseModel):
    product_id: int
    qty: int


class SaleEntryIn(BaseModel):
    sale_id: int
    store: int
    date: dt.date
    total: float
    tax: float
    lines: list[EntryLine] = Field(default_factory=list)


class RefundEntryIn(BaseModel):
    return_id: int
    sale_id: int
    store: int
    date: dt.date
    refund_amount: float


@APP.post("/internal/ledger/sales")
def record_sale(inp: SaleEntryIn):
    """Step record_sale. A repeated delivery answers as before."""
    with transaction() as cur:
        if start_step(cur, "record_sale") is None:
            cur.execute("INSERT INTO sale_entries (sale_id, store_id, sold_on, total, tax) VALUES (%s,%s,%s,%s,%s)",
                        (inp.sale_id, inp.store, inp.date, money(inp.total), money(inp.tax)))
            for n, line in enumerate(inp.lines, start=1):
                cur.execute("INSERT INTO sale_entry_lines (sale_id, line_no, product_id, qty) VALUES (%s,%s,%s,%s)",
                            (inp.sale_id, n, line.product_id, line.qty))
            finish_step(cur, "record_sale", {"sale_id": inp.sale_id})
    return {"sale_id": inp.sale_id}


@APP.post("/internal/ledger/refunds")
def record_refund(inp: RefundEntryIn):
    """Step record_refund. A repeated delivery answers as before."""
    with transaction() as cur:
        if start_step(cur, "record_refund") is None:
            cur.execute("INSERT INTO refund_entries (return_id, sale_id, store_id, refunded_on, refund_amount)"
                        " VALUES (%s,%s,%s,%s,%s)",
                        (inp.return_id, inp.sale_id, inp.store, inp.date, money(inp.refund_amount)))
            finish_step(cur, "record_refund", {"return_id": inp.return_id})
    return {"return_id": inp.return_id}


def remove_sale(cur, changes) -> None:
    if changes:
        cur.execute("DELETE FROM sale_entry_lines WHERE sale_id=%s", (changes["sale_id"],))
        cur.execute("DELETE FROM sale_entries WHERE sale_id=%s", (changes["sale_id"],))


def remove_refund(cur, changes) -> None:
    if changes:
        cur.execute("DELETE FROM refund_entries WHERE return_id=%s", (changes["return_id"],))


# Shared code: every writer has the undo. Till never undoes a ledger entry.
install_undo(APP, {"record_sale": remove_sale, "record_refund": remove_refund})


# --- sales report ------------------------------------------------------------------

@APP.get("/reports/sales")
def sales_report(store: int, to: date, from_: date = Query(alias="from")):
    with transaction() as cur:
        require(cur, "store", "SELECT store_id FROM stores WHERE store_id=%s", store)
        sales = one(cur, "SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS gross, COALESCE(SUM(tax),0) AS tax"
                         " FROM sale_entries WHERE store_id=%s AND sold_on BETWEEN %s AND %s", store, from_, to)
        refunds = one(cur, "SELECT COALESCE(SUM(refund_amount),0) AS r FROM refund_entries"
                           " WHERE store_id=%s AND refunded_on BETWEEN %s AND %s", store, from_, to)["r"]
        cur.execute("SELECT l.product_id, SUM(l.qty) AS qty FROM sale_entry_lines l"
                    " JOIN sale_entries e ON e.sale_id = l.sale_id"
                    " WHERE e.store_id=%s AND e.sold_on BETWEEN %s AND %s"
                    " GROUP BY l.product_id ORDER BY qty DESC, l.product_id LIMIT 5", (store, from_, to))
        top = [{"product_id": r["product_id"], "qty": int(r["qty"])} for r in cur.fetchall()]
    gross, refunds = money(sales["gross"]), money(refunds)
    return {"store": store, "from": from_.isoformat(), "to": to.isoformat(), "sales_count": sales["n"],
            "gross_total": float(gross), "tax_total": float(money(sales["tax"])),
            "refunds_total": float(refunds), "net_revenue": float(gross - refunds), "top_products": top}

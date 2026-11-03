"""reporting: sales reporting for head office and finance (variant B). Keeps a
ledger of sale and refund entries, delivered by till's outbox, and answers the
sales report from it."""
from datetime import date

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

from common import calllog, seed
from common.db import create_schema, one, require, schema_file, transaction, wait_for_db
from common.money import money
from common.receipts import SCHEMA as RECEIPTS, router as undo_router, run_step, undo_handler

SERVICE = "reporting"

calllog.init(SERVICE)
APP = FastAPI(title="reporting")
APP.add_middleware(calllog.CallLog)
APP.include_router(undo_router)


def fill_from_seed(cur, data: dict) -> None:
    for s in data["stores"]:
        cur.execute("INSERT INTO stores (store_id) VALUES (%s)", (s["SID"],))


@APP.on_event("startup")
def start():
    wait_for_db()
    create_schema(schema_file(__file__), RECEIPTS)
    seed.load_once("stores", fill_from_seed)


@APP.get("/health")
def health():
    return {"status": "ok"}


# --- internal: ledger entries from till (steps record_sale, record_refund) ---------------------------

class EntryLine(BaseModel):
    product_id: int
    qty: int


class VatLine(BaseModel):
    rate: float
    net: float
    vat: float
    gross: float


class SaleEntry(BaseModel):
    sale_id: int
    store: int
    date: date
    total: float
    tax: float
    vat: list[VatLine]
    lines: list[EntryLine] = Field(min_length=1)


class RefundEntry(BaseModel):
    return_id: int
    sale_id: int
    store: int
    date: date
    refund_amount: float


@APP.post("/internal/ledger/sales")
def record_sale(entry: SaleEntry):
    def apply(cur):
        cur.execute("INSERT INTO sale_entries (sale_id, store_id, sold_on, total, tax) VALUES (%s,%s,%s,%s,%s)",
                    (entry.sale_id, entry.store, entry.date, str(money(entry.total)), str(money(entry.tax))))
        for n, line in enumerate(entry.lines, 1):
            cur.execute("INSERT INTO sale_entry_lines (sale_id, line_no, product_id, qty) VALUES (%s,%s,%s,%s)",
                        (entry.sale_id, n, line.product_id, line.qty))
        for v in entry.vat:
            cur.execute("INSERT INTO sale_entry_vat (sale_id, rate, net, vat, gross) VALUES (%s,%s,%s,%s,%s)",
                        (entry.sale_id, str(v.rate), str(money(v.net)), str(money(v.vat)), str(money(v.gross))))
        return {"sale_id": entry.sale_id}

    return run_step("record_sale", apply, lambda cur, changes: changes)


@APP.post("/internal/ledger/refunds")
def record_refund(entry: RefundEntry):
    def apply(cur):
        cur.execute("INSERT INTO refund_entries (return_id, sale_id, store_id, refunded_on, refund_amount)"
                    " VALUES (%s,%s,%s,%s,%s)", (entry.return_id, entry.sale_id, entry.store, entry.date,
                                                 str(money(entry.refund_amount))))
        return {"return_id": entry.return_id}

    return run_step("record_refund", apply, lambda cur, changes: changes)


@undo_handler("record_sale")
def undo_record_sale(cur, changes):
    cur.execute("DELETE FROM sale_entry_lines WHERE sale_id=%s", (changes["sale_id"],))
    cur.execute("DELETE FROM sale_entry_vat WHERE sale_id=%s", (changes["sale_id"],))
    cur.execute("DELETE FROM sale_entries WHERE sale_id=%s", (changes["sale_id"],))


@undo_handler("record_refund")
def undo_record_refund(cur, changes):
    cur.execute("DELETE FROM refund_entries WHERE return_id=%s", (changes["return_id"],))


# --- sales report ---------------------------------------------------------------------------------

@APP.get("/reports/sales")
def sales_report(store: int, to: date, from_: date = Query(alias="from")):
    with transaction() as cur:
        require(cur, "store", "SELECT store_id FROM stores WHERE store_id=%s", store)
        sales = one(cur, "SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS gross, COALESCE(SUM(tax),0) AS tax"
                         " FROM sale_entries WHERE store_id=%s AND sold_on BETWEEN %s AND %s", store, from_, to)
        refunds = one(cur, "SELECT COALESCE(SUM(refund_amount),0) AS r FROM refund_entries"
                           " WHERE store_id=%s AND refunded_on BETWEEN %s AND %s", store, from_, to)["r"]
        cur.execute("SELECT l.product_id, SUM(l.qty) AS qty FROM sale_entry_lines l"
                    " JOIN sale_entries s ON s.sale_id = l.sale_id"
                    " WHERE s.store_id=%s AND s.sold_on BETWEEN %s AND %s"
                    " GROUP BY l.product_id ORDER BY qty DESC, l.product_id LIMIT 5", (store, from_, to))
        top = [{"product_id": r["product_id"], "qty": int(r["qty"])} for r in cur.fetchall()]
        cur.execute("SELECT v.rate, SUM(v.net) AS net, SUM(v.vat) AS vat, SUM(v.gross) AS gross FROM sale_entry_vat v"
                    " JOIN sale_entries s ON s.sale_id = v.sale_id WHERE s.store_id=%s AND s.sold_on BETWEEN %s AND %s"
                    " GROUP BY v.rate ORDER BY v.rate", (store, from_, to))
        vat = [{"rate": float(r["rate"]), "net": float(money(r["net"])), "vat": float(money(r["vat"])),
                "gross": float(money(r["gross"]))} for r in cur.fetchall()]
        gross, refunds = money(sales["gross"]), money(refunds)
        return {"store": store, "from": from_.isoformat(), "to": to.isoformat(), "sales_count": sales["n"],
                "gross_total": float(gross), "vat": vat, "tax_total": float(sum((money(v["vat"]) for v in vat), 0)),
                "refunds_total": float(refunds), "net_revenue": float(gross - refunds), "top_products": top}

"""till: selling at the till (variant B). Register shifts and the Z-report, sales,
returns and refunds, gift cards, stock on hand, VAT by category. Keeps a copy of the
price list (source: purchasing) and delivers ledger entries to reporting through
the outbox (docs/design.md, variant B)."""
import sys
import threading
import time
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from common import calllog, outbox, seed
from common.client import call, expect, undo
from common.db import create_schema, one, require, schema_file, transaction, wait_for_db
from common.money import money, now
from common.receipts import SCHEMA as RECEIPTS, router as undo_router, run_step, undo_handler

SERVICE = "till"
LEDGER = {"sale": "/internal/ledger/sales", "refund": "/internal/ledger/refunds"}
PRICE_LIST_EVERY = 60.0
REDUCED = {"Dairy", "Produce", "Beef", "Poultry", "Pasta", "DryGoods", "PetFood"}  # CR1: 2.6 %, the rest 8.1 %

calllog.init(SERVICE)
APP = FastAPI(title="till")
APP.add_middleware(calllog.CallLog)
APP.include_router(undo_router)


def fail(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


# --- start: schema, seed, background tasks ----------------------------------------

def fill_from_seed(cur, data: dict) -> None:
    for r in data["store_registers"]:
        cur.execute("INSERT INTO registers (register_no, store_id) VALUES (%s,%s)", (r["register_num"], r["SID"]))
    for e in data["employee_info"]:
        cur.execute("INSERT INTO staff (staff_id) VALUES (%s)", (e["employee_id"],))
    for p in data["product_inventory"]:
        cur.execute("INSERT INTO price_list (product_id, unit_price, category) VALUES (%s,%s,%s)",
                    (p["product_id"], str(money(p["unit_price"])), p["productType"]))
        cur.execute("INSERT INTO stock (product_id, on_hand) VALUES (%s,%s)", (p["product_id"], p["in_stock"]))
    for g in data["gift_card"]:
        cur.execute("INSERT INTO gift_cards (gift_card_id, balance) VALUES (%s,%s)",
                    (g["gift_id"], str(money(g["card_balance"]))))


def refresh_price_list() -> None:
    """Pulls the price list from purchasing; on failure the last copy stays."""
    try:
        prices = expect(call("purchasing", "GET", "/internal/price-list", request_id=calllog.new_request_id()))
        with transaction() as cur:
            for p in prices:
                cur.execute("INSERT INTO price_list (product_id, unit_price, category) VALUES (%s,%s,%s)"
                            " ON DUPLICATE KEY UPDATE unit_price=VALUES(unit_price), category=VALUES(category)",
                            (p["product_id"], str(money(p["unit_price"])), p["category"]))
    except Exception as error:  # noqa: BLE001
        print(f"price list refresh failed, keeping the last copy: {error!r}", file=sys.stderr, flush=True)


def price_list_loop() -> None:
    while True:
        time.sleep(PRICE_LIST_EVERY)
        refresh_price_list()


@APP.on_event("startup")
def start():
    wait_for_db()
    create_schema(schema_file(__file__), RECEIPTS, outbox.SCHEMA)
    seed.load_once("registers", fill_from_seed)
    threading.Thread(target=price_list_loop, name="price-list", daemon=True).start()
    outbox.start_retry("reporting", LEDGER)


@APP.get("/health")
def health():
    return {"status": "ok"}


# --- helpers ------------------------------------------------------------------------

def register_of(cur, register: int, lock: bool = False):
    return require(cur, "register", "SELECT * FROM registers WHERE register_no=%s" + (" FOR UPDATE" if lock else ""),
                   register)


def open_shift(cur, register: int, lock: bool = False):
    return one(cur, "SELECT * FROM shifts WHERE register_no=%s AND closed_at IS NULL"
               + (" FOR UPDATE" if lock else ""), register)


def require_staff(cur, staff_id: int) -> None:
    require(cur, "employee", "SELECT staff_id FROM staff WHERE staff_id=%s", staff_id)


def shift_still_open(cur, shift_id: int, register: int) -> None:
    """Shared lock on the shift row: a close waits for this transaction, or this one sees it closed."""
    shift = one(cur, "SELECT closed_at FROM shifts WHERE shift_id=%s LOCK IN SHARE MODE", shift_id)
    if shift is None or shift["closed_at"] is not None:
        raise fail(409, f"register {register} is not open")


def vat_rate(category: str) -> Decimal:
    return Decimal("0.026") if category in REDUCED else Decimal("0.081")


def vat_lines(gross_by_rate: dict[Decimal, Decimal]) -> list[dict]:
    """CR1: per rate gross, vat = gross x rate / (1 + rate), net = gross - vat; lowest rate first."""
    lines = []
    for rate in sorted(gross_by_rate):
        gross = money(gross_by_rate[rate])
        vat = money(gross * rate / (1 + rate))
        lines.append({"rate": rate, "net": gross - vat, "vat": vat, "gross": gross})
    return lines


def vat_body(lines) -> list[dict]:
    return [{"rate": float(l["rate"]), "net": float(money(l["net"])), "vat": float(money(l["vat"])),
             "gross": float(money(l["gross"]))} for l in lines]


def added_up(lines) -> dict[int, int]:
    wanted: dict[int, int] = {}
    for line in lines:
        wanted[line.product_id] = wanted.get(line.product_id, 0) + line.qty
    return wanted


def deliver_ledger(entry_id: int) -> None:
    outbox.deliver("reporting", LEDGER, entry_id)


# --- gift cards ------------------------------------------------------------------------

class GiftCardIn(BaseModel):
    amount: float = Field(gt=0)


@APP.post("/gift-cards", status_code=201)
def issue_gift_card(inp: GiftCardIn):
    with transaction() as cur:
        cur.execute("INSERT INTO gift_cards (balance) VALUES (%s)", (str(money(inp.amount)),))
        return {"gift_card_id": cur.lastrowid, "balance": float(money(inp.amount))}


@APP.get("/gift-cards/{gift_card_id}")
def get_gift_card(gift_card_id: int):
    with transaction() as cur:
        card = require(cur, "gift card", "SELECT * FROM gift_cards WHERE gift_card_id=%s", gift_card_id)
        return {"gift_card_id": card["gift_card_id"], "balance": float(money(card["balance"]))}


# --- registers: shifts and the Z-report ---------------------------------------------------

class OpenIn(BaseModel):
    employee_id: int
    opening_cash: float = Field(ge=0)


class CloseIn(BaseModel):
    employee_id: int
    counted_cash: float = Field(ge=0)


@APP.post("/registers/{register}/open", status_code=201)
def open_register(register: int, inp: OpenIn):
    with transaction() as cur:
        require_staff(cur, inp.employee_id)
        register_of(cur, register, lock=True)
        if open_shift(cur, register):
            raise fail(409, f"register {register} is already open")
        opened = now()
        cur.execute("INSERT INTO shifts (register_no, opened_by, opened_at, opening_cash) VALUES (%s,%s,%s,%s)",
                    (register, inp.employee_id, opened.replace(tzinfo=None), str(money(inp.opening_cash))))
        return {"session_id": cur.lastrowid, "register": register, "opened_at": opened.isoformat(timespec="seconds")}


@APP.post("/registers/{register}/close")
def close_register(register: int, inp: CloseIn):
    with transaction() as cur:
        require_staff(cur, inp.employee_id)
        register_of(cur, register, lock=True)
        shift = open_shift(cur, register, lock=True)
        if not shift:
            raise fail(409, f"register {register} is not open")
        shift_id = shift["shift_id"]
        sales = one(cur, "SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS gross, COALESCE(SUM(tax),0) AS tax"
                         " FROM sales WHERE shift_id=%s", shift_id)
        cash = one(cur, "SELECT COALESCE(SUM(p.amount),0) AS cash FROM payments p JOIN sales s ON s.sale_id=p.sale_id"
                        " WHERE s.shift_id=%s AND p.tender='cash'", shift_id)["cash"]
        refunds = one(cur, "SELECT COALESCE(SUM(refund_amount),0) AS r FROM returns WHERE shift_id=%s", shift_id)["r"]
        cur.execute("SELECT v.rate, SUM(v.net) AS net, SUM(v.vat) AS vat, SUM(v.gross) AS gross FROM sale_vat v"
                    " JOIN sales s ON s.sale_id=v.sale_id WHERE s.shift_id=%s GROUP BY v.rate ORDER BY v.rate",
                    (shift_id,))
        vat = cur.fetchall()
        opening = money(shift["opening_cash"])
        expected = opening + money(cash) - money(refunds)
        counted = money(inp.counted_cash)
        cur.execute("UPDATE shifts SET closed_by=%s, closed_at=%s, counted_cash=%s WHERE shift_id=%s",
                    (inp.employee_id, now().replace(tzinfo=None), str(counted), shift_id))
        return {"session_id": shift_id, "register": register, "sales_count": sales["n"],
                "gross_total": float(money(sales["gross"])), "vat": vat_body(vat),
                "tax_total": float(sum((money(v["vat"]) for v in vat), Decimal(0))),
                "refunds_total": float(money(refunds)), "cash_sales": float(money(cash)),
                "opening_cash": float(opening), "cash_expected": float(expected),
                "counted_cash": float(counted), "difference": float(counted - expected)}


# --- sales (checkout) ------------------------------------------------------------------------

class Line(BaseModel):
    product_id: int
    qty: int = Field(ge=1)


class Payment(BaseModel):
    method: str = Field(pattern="^(cash|card|gift_card)$")
    amount: float = Field(gt=0)
    gift_card_id: int | None = None


class SaleIn(BaseModel):
    register: int
    employee_id: int
    customer_id: int | None = None
    lines: list[Line] = Field(min_length=1)
    payments: list[Payment] = Field(min_length=1)


def sale_body(cur, sale_id: int) -> dict:
    s = require(cur, "sale", "SELECT * FROM sales WHERE sale_id=%s", sale_id)
    cur.execute("SELECT product_id, qty, unit_price FROM sale_lines WHERE sale_id=%s ORDER BY line_no", (sale_id,))
    lines = [{"product_id": l["product_id"], "qty": l["qty"], "unit_price": float(money(l["unit_price"])),
              "line_total": float(money(l["qty"] * money(l["unit_price"])))} for l in cur.fetchall()]
    cur.execute("SELECT tender, gift_card_id, amount FROM payments WHERE sale_id=%s ORDER BY line_no", (sale_id,))
    paid = cur.fetchall()
    payments = []
    for tender in ("cash", "card"):
        amount = sum((money(p["amount"]) for p in paid if p["tender"] == tender), Decimal(0))
        if amount:
            payments.append({"method": tender, "amount": float(amount)})
    payments += [{"method": "gift_card", "gift_card_id": p["gift_card_id"], "amount": float(money(p["amount"]))}
                 for p in paid if p["tender"] == "gift_card"]
    cur.execute("SELECT rate, net, vat, gross FROM sale_vat WHERE sale_id=%s ORDER BY rate", (sale_id,))
    vat = vat_body(cur.fetchall())
    return {"sale_id": sale_id, "register": s["register_no"], "date": s["sold_on"].isoformat(),
            "customer_id": s["customer_id"], "lines": lines, "subtotal": float(money(s["subtotal"])),
            "tax": float(money(s["tax"])), "total": float(money(s["total"])), "vat": vat,
            "reward_points_earned": s["reward_points_earned"], "tier": s["tier"], "payments": payments}


def gift_card_sums(payments) -> dict[int, Decimal]:
    sums: dict[int, Decimal] = {}
    for p in payments:
        if p.method == "gift_card":
            if p.gift_card_id is None:
                raise fail(422, "gift card payment without gift_card_id")
            sums[p.gift_card_id] = sums.get(p.gift_card_id, Decimal(0)) + money(p.amount)
    return sums


def check_stock(cur, wanted: dict[int, int], lock: bool = False) -> None:
    for product_id in sorted(wanted) if lock else wanted:
        row = one(cur, "SELECT on_hand FROM stock WHERE product_id=%s" + (" FOR UPDATE" if lock else ""), product_id)
        if row is None or row["on_hand"] < wanted[product_id]:
            raise fail(409, f"not enough stock for product {product_id}")


def check_gift_cards(cur, sums: dict[int, Decimal], lock: bool = False) -> None:
    for gift_card_id in sorted(sums) if lock else sums:
        card = require(cur, "gift card", "SELECT balance FROM gift_cards WHERE gift_card_id=%s"
                       + (" FOR UPDATE" if lock else ""), gift_card_id)
        if money(card["balance"]) < sums[gift_card_id]:
            raise fail(409, f"gift card {gift_card_id} balance too low")


@APP.post("/sales", status_code=201)
def create_sale(inp: SaleIn):
    # 1-7: checks, read without locks
    with transaction() as cur:
        store_id = register_of(cur, inp.register)["store_id"]
        shift = open_shift(cur, inp.register)
        if not shift:
            raise fail(409, f"register {inp.register} is not open")
        require_staff(cur, inp.employee_id)
        wanted = added_up(inp.lines)
        prices, rates = {}, {}
        for product_id in wanted:
            entry = require(cur, "product", "SELECT unit_price, category FROM price_list WHERE product_id=%s", product_id)
            prices[product_id], rates[product_id] = money(entry["unit_price"]), vat_rate(entry["category"])
        check_stock(cur, wanted)
        gross_by_rate: dict[Decimal, Decimal] = {}
        for line in inp.lines:
            rate = rates[line.product_id]
            gross_by_rate[rate] = gross_by_rate.get(rate, Decimal(0)) + line.qty * prices[line.product_id]
        vat = vat_lines(gross_by_rate)
        total = sum((v["gross"] for v in vat), Decimal(0))
        tax = sum((v["vat"] for v in vat), Decimal(0))
        subtotal = total - tax
        paid = sum((money(p.amount) for p in inp.payments), Decimal(0))
        if paid != total:
            raise fail(422, f"payments add up to {paid}, but the total is {total}")
        cards = gift_card_sums(inp.payments)
        check_gift_cards(cur, cards)

    # 8: reward points in customers (step earn_points)
    points, tier, points_per_chf = 0, None, None
    if inp.customer_id is not None:
        try:
            earned = expect(call("customers", "POST", f"/internal/customers/{inp.customer_id}/earn",
                                 {"total": float(total), "date": now().date().isoformat()}))
            points, tier, points_per_chf = earned["points_earned"], earned["tier"], earned["points_per_chf"]
        except HTTPException:
            undo("customers", "earn_points")
            raise

    # 9: own transaction, rows locked and checked again
    try:
        with transaction() as cur:
            shift_still_open(cur, shift["shift_id"], inp.register)
            check_stock(cur, wanted, lock=True)
            check_gift_cards(cur, cards, lock=True)
            at = now()
            cur.execute("INSERT INTO sales (shift_id, register_no, store_id, sold_on, sold_at, staff_id, customer_id,"
                        " subtotal, tax, total, reward_points_earned, tier, points_per_chf)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (shift["shift_id"], inp.register, store_id, at.date(), at.replace(tzinfo=None),
                         inp.employee_id, inp.customer_id, str(subtotal), str(tax), str(total), points, tier,
                         points_per_chf))
            sale_id = cur.lastrowid
            for v in vat:
                cur.execute("INSERT INTO sale_vat (sale_id, rate, net, vat, gross) VALUES (%s,%s,%s,%s,%s)",
                            (sale_id, str(v["rate"]), str(v["net"]), str(v["vat"]), str(v["gross"])))
            for n, line in enumerate(inp.lines, 1):
                cur.execute("INSERT INTO sale_lines (sale_id, line_no, product_id, qty, unit_price)"
                            " VALUES (%s,%s,%s,%s,%s)", (sale_id, n, line.product_id, line.qty,
                                                         str(prices[line.product_id])))
            for n, p in enumerate(inp.payments, 1):
                cur.execute("INSERT INTO payments (sale_id, line_no, tender, gift_card_id, amount)"
                            " VALUES (%s,%s,%s,%s,%s)", (sale_id, n, p.method,
                                                         p.gift_card_id if p.method == "gift_card" else None,
                                                         str(money(p.amount))))
            for product_id, qty in wanted.items():
                cur.execute("UPDATE stock SET on_hand = on_hand - %s WHERE product_id=%s", (qty, product_id))
            for gift_card_id, amount in cards.items():
                cur.execute("UPDATE gift_cards SET balance = balance - %s WHERE gift_card_id=%s",
                            (str(amount), gift_card_id))
            entry_id = outbox.add(cur, "sale", {
                "sale_id": sale_id, "store": store_id, "date": at.date().isoformat(), "total": float(total),
                "tax": float(tax), "vat": vat_body(vat),
                "lines": [{"product_id": l.product_id, "qty": l.qty} for l in inp.lines]})
    except BaseException:
        if inp.customer_id is not None:
            undo("customers", "earn_points")
        raise

    # 10: after the commit, the ledger entry goes to reporting (a failure stays in the outbox)
    deliver_ledger(entry_id)
    with transaction() as cur:
        return sale_body(cur, sale_id)


@APP.get("/sales/{sale_id}")
def get_sale(sale_id: int):
    with transaction() as cur:
        return sale_body(cur, sale_id)


# --- returns ---------------------------------------------------------------------------------

class ReturnIn(BaseModel):
    sale_id: int
    register: int
    employee_id: int
    lines: list[Line] = Field(min_length=1)


def returnable(cur, sale_id: int, wanted: dict[int, int]) -> Decimal:
    """Checks the lines against sold minus returned; answers the net amount."""
    cur.execute("SELECT product_id, SUM(qty) AS qty, MAX(unit_price) AS unit_price FROM sale_lines"
                " WHERE sale_id=%s GROUP BY product_id", (sale_id,))
    sold = {r["product_id"]: r for r in cur.fetchall()}
    cur.execute("SELECT l.product_id, SUM(l.qty) AS qty FROM return_lines l JOIN returns r ON r.return_id=l.return_id"
                " WHERE r.sale_id=%s GROUP BY l.product_id", (sale_id,))
    returned = {r["product_id"]: int(r["qty"]) for r in cur.fetchall()}
    net = Decimal(0)
    for product_id, qty in wanted.items():
        if product_id not in sold:
            raise fail(409, f"product {product_id} is not part of sale {sale_id}, cannot return it")
        if returned.get(product_id, 0) + qty > int(sold[product_id]["qty"]):
            raise fail(409, f"cannot return more of product {product_id} than was sold")
        net += qty * money(sold[product_id]["unit_price"])
    return net


@APP.post("/returns", status_code=201)
def create_return(inp: ReturnIn):
    wanted = added_up(inp.lines)
    with transaction() as cur:
        sale = require(cur, "sale", "SELECT * FROM sales WHERE sale_id=%s", inp.sale_id)
        store_id = register_of(cur, inp.register)["store_id"]
        shift = open_shift(cur, inp.register)
        if not shift:
            raise fail(409, f"register {inp.register} is not open")
        require_staff(cur, inp.employee_id)
        refund = money(returnable(cur, inp.sale_id, wanted))  # CR1: the gross price

    # CR2: a return of a sale with a customer takes the points back (step refund_points)
    if sale["customer_id"] is not None:
        try:
            expect(call("customers", "POST", f"/internal/customers/{sale['customer_id']}/refund",
                        {"sale_date": sale["sold_on"].isoformat(), "refund_amount": float(refund),
                         "points_per_chf": sale["points_per_chf"]}))
        except HTTPException:
            undo("customers", "refund_points")
            raise

    try:
        return_id, entry_id = write_return(inp, wanted, shift, store_id, refund)
    except BaseException:
        if sale["customer_id"] is not None:
            undo("customers", "refund_points")
        raise

    deliver_ledger(entry_id)
    return {"return_id": return_id, "sale_id": inp.sale_id,
            "lines": [{"product_id": p, "qty": q} for p, q in wanted.items()], "refund_amount": float(refund)}


def write_return(inp: ReturnIn, wanted: dict[int, int], shift: dict, store_id: int, refund: Decimal):
    with transaction() as cur:
        shift_still_open(cur, shift["shift_id"], inp.register)
        one(cur, "SELECT sale_id FROM sales WHERE sale_id=%s FOR UPDATE", inp.sale_id)
        returnable(cur, inp.sale_id, wanted)
        at = now()
        cur.execute("INSERT INTO returns (sale_id, shift_id, register_no, store_id, returned_on, returned_at, staff_id,"
                    " refund_amount) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (inp.sale_id, shift["shift_id"], inp.register, store_id, at.date(), at.replace(tzinfo=None),
                     inp.employee_id, str(refund)))
        return_id = cur.lastrowid
        for product_id in sorted(wanted):
            cur.execute("INSERT INTO return_lines (return_id, product_id, qty) VALUES (%s,%s,%s)",
                        (return_id, product_id, wanted[product_id]))
            cur.execute("UPDATE stock SET on_hand = on_hand + %s WHERE product_id=%s", (wanted[product_id], product_id))
        entry_id = outbox.add(cur, "refund", {"return_id": return_id, "sale_id": inp.sale_id, "store": store_id,
                                              "date": at.date().isoformat(), "refund_amount": float(refund)})
    return return_id, entry_id


# --- internal: stock on hand for purchasing ------------------------------------------------------

class StockLines(BaseModel):
    lines: list[Line] = Field(min_length=1)


@APP.get("/internal/stock/{product_id}")
def stock_on_hand(product_id: int):
    with transaction() as cur:
        row = require(cur, "product", "SELECT on_hand FROM stock WHERE product_id=%s", product_id)
        return {"product_id": product_id, "on_hand": row["on_hand"]}


@APP.post("/internal/stock/receive")
def receive_stock(inp: StockLines):
    wanted = added_up(inp.lines)

    def apply(cur):
        for product_id in sorted(wanted):
            require(cur, "product", "SELECT on_hand FROM stock WHERE product_id=%s FOR UPDATE", product_id)
        for product_id in sorted(wanted):
            cur.execute("UPDATE stock SET on_hand = on_hand + %s WHERE product_id=%s", (wanted[product_id], product_id))
        return [{"product_id": p, "qty": wanted[p]} for p in sorted(wanted)]

    return run_step("receive_stock", apply, lambda cur, changes: {"lines": changes})


@undo_handler("receive_stock")
def undo_receive_stock(cur, changes):
    for line in changes:
        cur.execute("UPDATE stock SET on_hand = on_hand - %s WHERE product_id=%s", (line["qty"], line["product_id"]))

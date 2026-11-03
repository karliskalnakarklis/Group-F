"""till (variant B): selling at the till.
Register shifts and the Z-report, sales, returns and refunds, gift cards,
stock on hand and the tax rate, in till-db. Keeps copies of the price list
(source: purchasing), the registers of each store and the staff IDs.
Sale and refund entries go to reporting through the ledger outbox."""
import json
import threading
import time
import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from common.calllog import REQUEST_ID, STEP_KEY, Steps, call, call_ok, create_app, log, now
from common.db import (APPLIED_STEPS, fail, finish_step, init_database, install_undo, money, one, require,
                       start_step, transaction)

APP = create_app("till")
PRICE_LIST_EVERY = 60.0   # seconds
OUTBOX_EVERY = 2.0        # seconds

SCHEMA = """
CREATE TABLE IF NOT EXISTS registers (
  register int NOT NULL PRIMARY KEY, store int NOT NULL
);
CREATE TABLE IF NOT EXISTS staff (
  staff_id int NOT NULL PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS shifts (
  shift_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  register int NOT NULL, opened_by int NOT NULL, opened_at datetime NOT NULL,
  opening_cash decimal(12,2) NOT NULL,
  closed_by int DEFAULT NULL, closed_at datetime DEFAULT NULL, counted_cash decimal(12,2) DEFAULT NULL,
  KEY register (register)
);
CREATE TABLE IF NOT EXISTS price_list (
  product_id int NOT NULL PRIMARY KEY, unit_price decimal(12,2) NOT NULL
);
CREATE TABLE IF NOT EXISTS stock (
  product_id int NOT NULL PRIMARY KEY, on_hand int NOT NULL
);
CREATE TABLE IF NOT EXISTS tax_rates (
  tax_year int NOT NULL PRIMARY KEY, rate decimal(6,4) NOT NULL
);
CREATE TABLE IF NOT EXISTS gift_cards (
  gift_card_id int NOT NULL AUTO_INCREMENT PRIMARY KEY, balance decimal(12,2) NOT NULL
);
CREATE TABLE IF NOT EXISTS sales (
  sale_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  shift_id int NOT NULL, register int NOT NULL, sold_on date NOT NULL, sold_at datetime NOT NULL,
  staff_id int NOT NULL, customer_id int DEFAULT NULL,
  subtotal decimal(12,2) NOT NULL, tax decimal(12,2) NOT NULL, tax_rate decimal(6,4) NOT NULL,
  total decimal(12,2) NOT NULL, points_earned int NOT NULL DEFAULT 0,
  KEY shift (shift_id)
);
CREATE TABLE IF NOT EXISTS sale_lines (
  sale_id int NOT NULL, line_no int NOT NULL, product_id int NOT NULL, qty int NOT NULL,
  unit_price decimal(12,2) NOT NULL,
  PRIMARY KEY (sale_id, line_no)
);
CREATE TABLE IF NOT EXISTS payments (
  sale_id int NOT NULL, line_no int NOT NULL, tender varchar(10) NOT NULL, gift_card_id int DEFAULT NULL,
  amount decimal(12,2) NOT NULL,
  PRIMARY KEY (sale_id, line_no)
);
CREATE TABLE IF NOT EXISTS returns (
  return_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  sale_id int NOT NULL, shift_id int NOT NULL, register int NOT NULL,
  returned_on date NOT NULL, returned_at datetime NOT NULL, staff_id int NOT NULL,
  refund_amount decimal(12,2) NOT NULL,
  KEY sale (sale_id), KEY shift (shift_id)
);
CREATE TABLE IF NOT EXISTS return_lines (
  return_id int NOT NULL, product_id int NOT NULL, qty int NOT NULL,
  PRIMARY KEY (return_id, product_id)
);
CREATE TABLE IF NOT EXISTS ledger_outbox (
  entry_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  request_id varchar(100) NOT NULL, kind varchar(10) NOT NULL, payload text NOT NULL,
  created_at datetime NOT NULL, delivered_at datetime DEFAULT NULL,
  KEY undelivered (delivered_at, entry_id)
);
""" + APPLIED_STEPS


def fill(cur, seed: dict) -> None:
    """From the legacy tables: store_registers -> registers, employee_info ->
    staff IDs only, product_inventory -> price list copy and stock on hand,
    tax_table -> tax rates, gift_card -> gift cards."""
    for r in seed["store_registers"]:
        cur.execute("INSERT INTO registers (register, store) VALUES (%s,%s)", (r["register_num"], r["SID"]))
    for e in seed["employee_info"]:
        cur.execute("INSERT INTO staff (staff_id) VALUES (%s)", (e["employee_id"],))
    for p in seed["product_inventory"]:
        cur.execute("INSERT INTO price_list (product_id, unit_price) VALUES (%s,%s)",
                    (p["product_id"], money(p["unit_price"])))
        cur.execute("INSERT INTO stock (product_id, on_hand) VALUES (%s,%s)", (p["product_id"], p["in_stock"]))
    for t in seed["tax_table"]:
        cur.execute("INSERT INTO tax_rates (tax_year, rate) VALUES (%s,%s)", (t["tax_year"], str(t["tax_rate"])))
    for g in seed["gift_card"]:
        cur.execute("INSERT INTO gift_cards (gift_card_id, balance) VALUES (%s,%s)",
                    (g["gift_id"], money(g["card_balance"])))


@APP.on_event("startup")
def startup():
    init_database(SCHEMA, fill, "registers")
    threading.Thread(target=refresh_price_list_forever, daemon=True).start()
    threading.Thread(target=deliver_outbox_forever, daemon=True).start()


# --- helpers ---------------------------------------------------------------------------

class Line(BaseModel):
    product_id: int
    qty: int = Field(ge=1)


def added_up(lines: list[Line]) -> dict[int, int]:
    wanted: dict[int, int] = {}
    for line in lines:
        wanted[line.product_id] = wanted.get(line.product_id, 0) + line.qty
    return wanted


def require_staff(cur, staff_id: int) -> None:
    require(cur, "employee", "SELECT staff_id FROM staff WHERE staff_id=%s", staff_id)


def require_register(cur, register: int, lock: bool = False) -> dict:
    return require(cur, "register", "SELECT * FROM registers WHERE register=%s" + (" FOR UPDATE" if lock else ""),
                   register)


def open_shift_of(cur, register: int, lock: bool = False):
    return one(cur, "SELECT * FROM shifts WHERE register=%s AND closed_at IS NULL"
               + (" FOR UPDATE" if lock else ""), register)


def require_open_shift(cur, register: int) -> dict:
    """Register exists (404) and has an open shift (409)."""
    require_register(cur, register)
    shift = open_shift_of(cur, register)
    if not shift:
        raise fail(409, f"register {register} is not open")
    return shift


def hold_shift_open(cur, shift_id: int, register: int) -> None:
    """Shared lock on the shift row, so that a close waits for this sale or
    return, and check again that the shift is still open."""
    shift = one(cur, "SELECT closed_at FROM shifts WHERE shift_id=%s LOCK IN SHARE MODE", shift_id)
    if shift["closed_at"] is not None:
        raise fail(409, f"register {register} is not open")


def tax_rate(cur) -> Decimal:
    return Decimal(str(one(cur, "SELECT rate FROM tax_rates ORDER BY tax_year DESC LIMIT 1")["rate"]))


def store_of(cur, register: int) -> int:
    return require_register(cur, register)["store"]


# --- gift cards ------------------------------------------------------------------------

class GiftCardIn(BaseModel):
    amount: float = Field(gt=0)


@APP.post("/gift-cards", status_code=201)
def issue_gift_card(inp: GiftCardIn):
    with transaction() as cur:
        cur.execute("INSERT INTO gift_cards (balance) VALUES (%s)", (money(inp.amount),))
        return {"gift_card_id": cur.lastrowid, "balance": float(money(inp.amount))}


@APP.get("/gift-cards/{gift_card_id}")
def get_gift_card(gift_card_id: int):
    with transaction() as cur:
        card = require(cur, "gift card", "SELECT * FROM gift_cards WHERE gift_card_id=%s", gift_card_id)
        return {"gift_card_id": card["gift_card_id"], "balance": float(money(card["balance"]))}


# --- shifts (register sessions) ----------------------------------------------------------

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
        require_register(cur, register, lock=True)
        if open_shift_of(cur, register, lock=True):
            raise fail(409, f"register {register} is already open")
        opened = now()
        cur.execute("INSERT INTO shifts (register, opened_by, opened_at, opening_cash) VALUES (%s,%s,%s,%s)",
                    (register, inp.employee_id, opened.replace(tzinfo=None), money(inp.opening_cash)))
        return {"session_id": cur.lastrowid, "register": register, "opened_at": opened.isoformat(timespec="seconds")}


@APP.post("/registers/{register}/close")
def close_register(register: int, inp: CloseIn):
    """One transaction: the Z-report is computed while the shift row is locked,
    so it covers exactly the sales and returns of the shift."""
    counted = money(inp.counted_cash)
    with transaction() as cur:
        require_staff(cur, inp.employee_id)
        require_register(cur, register, lock=True)
        shift = open_shift_of(cur, register, lock=True)
        if not shift:
            raise fail(409, f"register {register} is not open")
        sid = shift["shift_id"]
        sales = one(cur, "SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS gross, COALESCE(SUM(tax),0) AS tax"
                         " FROM sales WHERE shift_id=%s", sid)
        cash = one(cur, "SELECT COALESCE(SUM(p.amount),0) AS cash FROM payments p JOIN sales s ON s.sale_id=p.sale_id"
                        " WHERE s.shift_id=%s AND p.tender='cash'", sid)["cash"]
        refunds = one(cur, "SELECT COALESCE(SUM(refund_amount),0) AS r FROM returns WHERE shift_id=%s", sid)["r"]
        cur.execute("UPDATE shifts SET closed_at=%s, closed_by=%s, counted_cash=%s WHERE shift_id=%s",
                    (now().replace(tzinfo=None), inp.employee_id, counted, sid))
    opening, cash, refunds = money(shift["opening_cash"]), money(cash), money(refunds)
    expected = opening + cash - refunds
    return {"session_id": sid, "register": register, "sales_count": sales["n"],
            "gross_total": float(money(sales["gross"])), "tax_total": float(money(sales["tax"])),
            "refunds_total": float(refunds), "cash_sales": float(cash),
            "opening_cash": float(opening), "cash_expected": float(expected),
            "counted_cash": float(counted), "difference": float(counted - expected)}


# --- sales -------------------------------------------------------------------------------

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
    payments = []
    for p in cur.fetchall():
        payment = {"method": p["tender"], "amount": float(money(p["amount"]))}
        if p["tender"] == "gift_card":
            payment["gift_card_id"] = p["gift_card_id"]
        payments.append(payment)
    return {"sale_id": sale_id, "register": s["register"], "date": s["sold_on"].isoformat(),
            "customer_id": s["customer_id"], "lines": lines, "subtotal": float(money(s["subtotal"])),
            "tax": float(money(s["tax"])), "total": float(money(s["total"])),
            "reward_points_earned": s["points_earned"], "payments": payments}


def check_stock(cur, wanted: dict[int, int], lock: bool) -> None:
    for product_id in sorted(wanted):
        row = one(cur, "SELECT on_hand FROM stock WHERE product_id=%s" + (" FOR UPDATE" if lock else ""), product_id)
        if row is None or row["on_hand"] < wanted[product_id]:
            raise fail(409, f"not enough stock for product {product_id}")


def gift_card_sums(payments: list[Payment]) -> dict[int, Decimal]:
    """Amount per gift card; several payments with one card count together."""
    sums: dict[int, Decimal] = {}
    for p in payments:
        if p.method == "gift_card":
            if p.gift_card_id is None:
                raise fail(422, "gift card payment without gift_card_id")
            sums[p.gift_card_id] = sums.get(p.gift_card_id, Decimal(0)) + money(p.amount)
    return sums


def check_gift_cards(cur, sums: dict[int, Decimal], lock: bool) -> None:
    for gift_card_id in sorted(sums):
        card = require(cur, "gift card", "SELECT balance FROM gift_cards WHERE gift_card_id=%s"
                       + (" FOR UPDATE" if lock else ""), gift_card_id)
        if money(card["balance"]) < sums[gift_card_id]:
            raise fail(409, f"gift card {gift_card_id} balance too low")


@APP.post("/sales", status_code=201)
def checkout(inp: SaleIn):
    wanted = added_up(inp.lines)
    # checks 1-7, without locks
    with transaction() as cur:
        shift = require_open_shift(cur, inp.register)
        require_staff(cur, inp.employee_id)
        prices = {}
        for product_id in wanted:
            prices[product_id] = money(require(cur, "product", "SELECT unit_price FROM price_list WHERE product_id=%s",
                                               product_id)["unit_price"])
        check_stock(cur, wanted, lock=False)
        rate = tax_rate(cur)
        subtotal = money(sum((line.qty * prices[line.product_id] for line in inp.lines), Decimal(0)))
        tax = money(subtotal * rate)
        total = subtotal + tax
        paid = sum((money(p.amount) for p in inp.payments), Decimal(0))
        if paid != total:
            raise fail(422, f"payments add up to {paid}, but the total is {total}")
        gift_sums = gift_card_sums(inp.payments)
        check_gift_cards(cur, gift_sums, lock=False)
        store = store_of(cur, inp.register)

    with Steps() as steps:
        points = 0
        if inp.customer_id is not None:
            points = steps.run("customers", "earn_points", f"/internal/customers/{inp.customer_id}/earn",
                               {"total": float(total)})["points_earned"]
        with transaction() as cur:
            # locks in a fixed order: shift, products by ID, gift cards by ID
            hold_shift_open(cur, shift["shift_id"], inp.register)
            check_stock(cur, wanted, lock=True)
            check_gift_cards(cur, gift_sums, lock=True)
            at = now()
            cur.execute("INSERT INTO sales (shift_id, register, sold_on, sold_at, staff_id, customer_id, subtotal,"
                        " tax, tax_rate, total, points_earned) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (shift["shift_id"], inp.register, at.date(), at.replace(tzinfo=None), inp.employee_id,
                         inp.customer_id, subtotal, tax, rate, total, points))
            sale_id = cur.lastrowid
            for n, line in enumerate(inp.lines, start=1):
                cur.execute("INSERT INTO sale_lines (sale_id, line_no, product_id, qty, unit_price)"
                            " VALUES (%s,%s,%s,%s,%s)", (sale_id, n, line.product_id, line.qty, prices[line.product_id]))
            for product_id in sorted(wanted):
                cur.execute("UPDATE stock SET on_hand = on_hand - %s WHERE product_id=%s", (wanted[product_id], product_id))
            for n, p in enumerate(inp.payments, start=1):
                cur.execute("INSERT INTO payments (sale_id, line_no, tender, gift_card_id, amount) VALUES (%s,%s,%s,%s,%s)",
                            (sale_id, n, p.method, p.gift_card_id if p.method == "gift_card" else None, money(p.amount)))
            for gift_card_id in sorted(gift_sums):
                cur.execute("UPDATE gift_cards SET balance = balance - %s WHERE gift_card_id=%s",
                            (gift_sums[gift_card_id], gift_card_id))
            entry_id = add_to_outbox(cur, "sale", {
                "sale_id": sale_id, "store": store, "date": at.date().isoformat(), "total": float(total),
                "tax": float(tax), "lines": [{"product_id": l.product_id, "qty": l.qty} for l in inp.lines]})
            body = sale_body(cur, sale_id)
    deliver(entry_id)
    return body


@APP.get("/sales/{sale_id}")
def get_sale(sale_id: int):
    with transaction() as cur:
        return sale_body(cur, sale_id)


# --- returns -------------------------------------------------------------------------------

class ReturnIn(BaseModel):
    sale_id: int
    register: int
    employee_id: int
    lines: list[Line] = Field(min_length=1)


def check_return(cur, sale_id: int, wanted: dict[int, int]) -> Decimal:
    """Every line is a product of the sale, and not more than sold minus
    already returned (409 return). Answers the net amount of the lines."""
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
        require(cur, "sale", "SELECT sale_id FROM sales WHERE sale_id=%s", inp.sale_id)
        shift = require_open_shift(cur, inp.register)
        require_staff(cur, inp.employee_id)
        check_return(cur, inp.sale_id, wanted)
        store = store_of(cur, inp.register)
    with transaction() as cur:
        hold_shift_open(cur, shift["shift_id"], inp.register)
        sale = one(cur, "SELECT * FROM sales WHERE sale_id=%s FOR UPDATE", inp.sale_id)
        net = check_return(cur, inp.sale_id, wanted)  # checked again, sale locked
        refund = money(net) + money(net * Decimal(str(sale["tax_rate"])))
        at = now()
        cur.execute("INSERT INTO returns (sale_id, shift_id, register, returned_on, returned_at, staff_id, refund_amount)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s)", (inp.sale_id, shift["shift_id"], inp.register, at.date(),
                                                      at.replace(tzinfo=None), inp.employee_id, refund))
        return_id = cur.lastrowid
        for product_id in sorted(wanted):
            cur.execute("INSERT INTO return_lines (return_id, product_id, qty) VALUES (%s,%s,%s)",
                        (return_id, product_id, wanted[product_id]))
            cur.execute("UPDATE stock SET on_hand = on_hand + %s WHERE product_id=%s", (wanted[product_id], product_id))
        entry_id = add_to_outbox(cur, "refund", {
            "return_id": return_id, "sale_id": inp.sale_id, "store": store, "date": at.date().isoformat(),
            "refund_amount": float(refund)})
    deliver(entry_id)
    return {"return_id": return_id, "sale_id": inp.sale_id,
            "lines": [{"product_id": p, "qty": q} for p, q in wanted.items()], "refund_amount": float(refund)}


# --- stock on hand (internal) ------------------------------------------------------------

@APP.get("/internal/stock/{product_id}")
def stock_on_hand(product_id: int):
    with transaction() as cur:
        row = require(cur, "product", "SELECT on_hand FROM stock WHERE product_id=%s", product_id)
    return {"product_id": product_id, "on_hand": row["on_hand"]}


class StockIn(BaseModel):
    lines: list[Line] = Field(min_length=1)


@APP.post("/internal/stock/receive")
def receive_stock(inp: StockIn):
    """Step receive_stock: all lines in one transaction with the receipt."""
    wanted = added_up(inp.lines)
    with transaction() as cur:
        earlier = start_step(cur, "receive_stock")
        if earlier is not None:
            return {"lines": earlier}
        for product_id in sorted(wanted):
            require(cur, "product", "SELECT on_hand FROM stock WHERE product_id=%s FOR UPDATE", product_id)
        changes = [{"product_id": p, "qty": wanted[p]} for p in sorted(wanted)]
        for line in changes:
            cur.execute("UPDATE stock SET on_hand = on_hand + %s WHERE product_id=%s", (line["qty"], line["product_id"]))
        finish_step(cur, "receive_stock", changes)
        return {"lines": changes}


def reverse_receive(cur, changes) -> None:
    for line in sorted(changes, key=lambda l: l["product_id"]):
        cur.execute("UPDATE stock SET on_hand = on_hand - %s WHERE product_id=%s", (line["qty"], line["product_id"]))


install_undo(APP, {"receive_stock": reverse_receive})


# --- ledger outbox -------------------------------------------------------------------------

LEDGER_PATHS = {"sale": "/internal/ledger/sales", "refund": "/internal/ledger/refunds"}


def add_to_outbox(cur, kind: str, payload: dict) -> int:
    """In the same transaction as the sale or return."""
    cur.execute("INSERT INTO ledger_outbox (request_id, kind, payload, created_at) VALUES (%s,%s,%s,%s)",
                (REQUEST_ID.get(), kind, json.dumps(payload), now().replace(tzinfo=None)))
    return cur.lastrowid


def deliver(entry_id: int) -> bool:
    """Send one outbox row to reporting with its original X-Request-Id and a new
    X-Step-Key; mark it delivered on 200. A failure never fails the sale or return."""
    try:
        with transaction() as cur:
            row = one(cur, "SELECT * FROM ledger_outbox WHERE entry_id=%s", entry_id)
        if row is None or row["delivered_at"] is not None:
            return True
        token = REQUEST_ID.set(row["request_id"])
        key_token = STEP_KEY.set(uuid.uuid4().hex)
        try:
            response = call("reporting", "POST", LEDGER_PATHS[row["kind"]], json_body=json.loads(row["payload"]))
        except HTTPException:
            return False
        finally:
            STEP_KEY.reset(key_token)
            REQUEST_ID.reset(token)
        if response.status_code != 200:
            log.warning("ledger entry %s refused: %s %s", entry_id, response.status_code, response.text)
            return False
        with transaction() as cur:
            cur.execute("UPDATE ledger_outbox SET delivered_at=%s WHERE entry_id=%s",
                        (now().replace(tzinfo=None), entry_id))
        return True
    except Exception:  # noqa: BLE001
        log.exception("delivering ledger entry %s failed", entry_id)
        return False


def deliver_outbox_forever() -> None:
    """Every 2 s: the undelivered rows, oldest first; stop at the first failure.
    Rows younger than one round are left to the delivery right after the commit."""
    while True:
        time.sleep(OUTBOX_EVERY)
        try:
            with transaction() as cur:
                cur.execute("SELECT entry_id FROM ledger_outbox WHERE delivered_at IS NULL AND created_at < %s"
                            " ORDER BY entry_id", (now().replace(tzinfo=None) - timedelta(seconds=OUTBOX_EVERY),))
                pending = [r["entry_id"] for r in cur.fetchall()]
            for entry_id in pending:
                if not deliver(entry_id):
                    break
        except Exception:  # noqa: BLE001
            log.exception("outbox round failed")


# --- price list copy -------------------------------------------------------------------------

def refresh_price_list() -> None:
    REQUEST_ID.set(uuid.uuid4().hex)
    STEP_KEY.set(uuid.uuid4().hex)
    prices = call_ok("purchasing", "GET", "/internal/price-list")
    with transaction() as cur:
        for p in prices:
            cur.execute("INSERT INTO price_list (product_id, unit_price) VALUES (%s,%s)"
                        " ON DUPLICATE KEY UPDATE unit_price=VALUES(unit_price)",
                        (p["product_id"], money(p["unit_price"])))


def refresh_price_list_forever() -> None:
    """Every 60 s; if the pull fails, the last copy stays."""
    while True:
        time.sleep(PRICE_LIST_EVERY)
        try:
            refresh_price_list()
        except Exception as error:  # noqa: BLE001
            log.warning("price list refresh failed, keeping the last copy: %s", getattr(error, "detail", error))

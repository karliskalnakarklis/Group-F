"""Frischwerk PoS monolith: one service, one database with the legacy schema.

It implements docs/contract.md, version 1. Everything runs in one process and
one database transaction per request; there are no calls to other services."""
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pymysql
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

APP = FastAPI(title="Frischwerk PoS monolith")
SERVICE = "gateway"
ZURICH = ZoneInfo("Europe/Zurich")
SEED = json.loads(Path(os.getenv("SEED_PATH", "/shared/seed.json")).read_text())
LOG_DIR = Path(os.getenv("CALL_LOG_DIR", "/logs"))
DB = dict(host=os.getenv("DB_HOST", "legacy-db"), user="pos", password=os.getenv("DB_PASSWORD", "pos"),
          database="pos", cursorclass=pymysql.cursors.DictCursor, autocommit=False)


# --- helpers -----------------------------------------------------------------

def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fail(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


@contextmanager
def transaction():
    conn = pymysql.connect(**DB)
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def one(cur, sql: str, *args):
    cur.execute(sql, args)
    return cur.fetchone()


def require(cur, what: str, sql: str, *args):
    row = one(cur, sql, *args)
    if row is None:
        raise fail(404, f"{what} not found")
    return row


def now() -> datetime:
    return datetime.now(ZURICH)


def open_session(cur, register: int, lock: bool = False):
    require(cur, "register", "SELECT * FROM store_registers WHERE register_num=%s", register)
    return one(cur, "SELECT * FROM registers_table WHERE register_num=%s AND close_time IS NULL"
               + (" FOR UPDATE" if lock else ""), register)


def tax_rate(cur) -> Decimal:
    row = one(cur, "SELECT tax_rate FROM tax_table ORDER BY tax_year DESC LIMIT 1")
    return Decimal(str(row["tax_rate"]))


# --- call log ------------------------------------------------------------------

@APP.middleware("http")
async def call_log(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    started = time.perf_counter()
    response = await call_next(request)
    entry = {
        "time": now().isoformat(timespec="milliseconds"), "service": SERVICE, "request_id": request_id,
        "direction": "in", "method": request.method, "target": SERVICE, "path": request.url.path,
        "status": response.status_code, "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    with (LOG_DIR / f"{SERVICE}.jsonl").open("a") as log:
        log.write(json.dumps(entry) + "\n")
    response.headers["X-Request-Id"] = request_id
    return response


# --- startup: schema and seed ----------------------------------------------------

@APP.on_event("startup")
def load_seed():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for _ in range(60):
        try:
            pymysql.connect(**DB).close()
            break
        except pymysql.err.OperationalError:
            time.sleep(1)
    statements = (Path(__file__).parent / "schema.sql").read_text().split(";")
    with transaction() as cur:
        for statement in statements:
            if statement.strip():
                cur.execute(statement)
        if one(cur, "SELECT COUNT(*) AS n FROM customer_info")["n"]:
            return
        for table, rows in SEED.items():
            if table.startswith("_"):
                continue
            for row in rows:
                columns = ", ".join(f"`{c}`" for c in row)
                cur.execute(f"INSERT INTO `{table}` ({columns}) VALUES ({', '.join(['%s'] * len(row))})",
                            list(row.values()))


@APP.get("/health")
def health():
    return {"status": "ok"}


# --- catalogue and customers ---------------------------------------------------------

def product_body(p: dict) -> dict:
    return {"product_id": p["product_id"], "name": p["productName"], "brand": p["brand"],
            "category": p["productType"], "unit_price": float(money(p["unit_price"])),
            "cost": float(money(p["cost"])), "in_stock": p["in_stock"], "vendor_id": p["vendor_id"]}


@APP.get("/products/{product_id}")
def get_product(product_id: int):
    with transaction() as cur:
        return product_body(require(cur, "product", "SELECT * FROM product_inventory WHERE product_id=%s", product_id))


class CustomerIn(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    street: str = ""
    zip_code: int = 0
    city: str = ""


def customer_body(c: dict) -> dict:
    return {"customer_id": c["customer_id"], "first_name": c["first_name"], "last_name": c["last_name"],
            "email": c["email"], "reward_points": int(c["rewards"] or 0)}


@APP.post("/customers", status_code=201)
def create_customer(inp: CustomerIn):
    phone = float("".join(ch for ch in inp.phone if ch.isdigit()) or 0)
    with transaction() as cur:
        cur.execute("INSERT INTO customer_info (email, password, first_name, last_name, phone_number, rewards,"
                    " street_address, city, state, zip_code) VALUES (%s,'',%s,%s,%s,0,%s,%s,'',%s)",
                    (inp.email, inp.first_name, inp.last_name, phone, inp.street, inp.city, inp.zip_code))
        return customer_body(one(cur, "SELECT * FROM customer_info WHERE customer_id=%s", cur.lastrowid))


@APP.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    with transaction() as cur:
        return customer_body(require(cur, "customer", "SELECT * FROM customer_info WHERE customer_id=%s", customer_id))


class GiftCardIn(BaseModel):
    amount: float = Field(gt=0)


@APP.post("/gift-cards", status_code=201)
def create_gift_card(inp: GiftCardIn):
    with transaction() as cur:
        cur.execute("INSERT INTO gift_card (promo_number, card_balance) VALUES (%s, %s)",
                    (uuid.uuid4().int % 10**8, float(money(inp.amount))))
        return {"gift_card_id": cur.lastrowid, "balance": float(money(inp.amount))}


@APP.get("/gift-cards/{gift_id}")
def get_gift_card(gift_id: int):
    with transaction() as cur:
        card = require(cur, "gift card", "SELECT * FROM gift_card WHERE gift_id=%s", gift_id)
        return {"gift_card_id": card["gift_id"], "balance": float(money(card["card_balance"]))}


# --- registers -------------------------------------------------------------------------

class OpenIn(BaseModel):
    employee_id: int
    opening_cash: float = Field(ge=0)


class CloseIn(BaseModel):
    employee_id: int
    counted_cash: float = Field(ge=0)


@APP.post("/registers/{register}/open", status_code=201)
def open_register(register: int, inp: OpenIn):
    with transaction() as cur:
        require(cur, "employee", "SELECT employee_id FROM employee_info WHERE employee_id=%s", inp.employee_id)
        if open_session(cur, register, lock=True):
            raise fail(409, f"register {register} is already open")
        opened = now()
        cur.execute("INSERT INTO registers_table (open_total, register_num, open_emp_id, open_time)"
                    " VALUES (%s,%s,%s,%s)", (float(money(inp.opening_cash)), register, inp.employee_id,
                                              opened.replace(tzinfo=None)))
        return {"session_id": cur.lastrowid, "register": register, "opened_at": opened.isoformat(timespec="seconds")}


@APP.post("/registers/{register}/close")
def close_register(register: int, inp: CloseIn):
    with transaction() as cur:
        require(cur, "employee", "SELECT employee_id FROM employee_info WHERE employee_id=%s", inp.employee_id)
        session = open_session(cur, register, lock=True)
        if not session:
            raise fail(409, f"register {register} is not open")
        sid = session["register_id"]
        sales = one(cur, "SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS gross, COALESCE(SUM(tax),0) AS tax,"
                         " COALESCE(SUM(cash),0) AS cash FROM ticket_system WHERE register_id=%s", sid)
        refunds = one(cur, "SELECT COALESCE(SUM(refunds),0) AS r FROM return_table WHERE register_id=%s", sid)["r"]
        opening = money(session["open_total"])
        expected = opening + money(sales["cash"]) - money(refunds)
        counted = money(inp.counted_cash)
        cur.execute("UPDATE registers_table SET close_total=%s, close_emp_id=%s, close_time=%s WHERE register_id=%s",
                    (float(counted), inp.employee_id, now().replace(tzinfo=None), sid))
        return {"session_id": sid, "register": register, "sales_count": sales["n"],
                "gross_total": float(money(sales["gross"])), "tax_total": float(money(sales["tax"])),
                "refunds_total": float(money(refunds)), "cash_sales": float(money(sales["cash"])),
                "opening_cash": float(opening), "cash_expected": float(expected),
                "counted_cash": float(counted), "difference": float(counted - expected)}


# --- sales -------------------------------------------------------------------------------

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


def sale_body(cur, ticket_id: int) -> dict:
    t = require(cur, "sale", "SELECT t.*, r.register_num FROM ticket_system t"
                " JOIN registers_table r ON r.register_id = t.register_id WHERE t.ticket_id=%s", ticket_id)
    cid = one(cur, "SELECT CID FROM cart_inprogress WHERE ticket_id=%s", ticket_id)["CID"]
    cur.execute("SELECT product_id, qty, unit_price FROM item_list WHERE CID=%s ORDER BY ITID", (cid,))
    lines = [{"product_id": i["product_id"], "qty": i["qty"], "unit_price": float(money(i["unit_price"])),
              "line_total": float(money(i["qty"] * money(i["unit_price"])))} for i in cur.fetchall()]
    payments = []
    if t["cash"]:
        payments.append({"method": "cash", "amount": float(money(t["cash"]))})
    if t["credit"]:
        payments.append({"method": "card", "amount": float(money(t["credit"]))})
    cur.execute("SELECT gift_id, amount FROM ticket_gift_payment WHERE ticket_id=%s", (ticket_id,))
    payments += [{"method": "gift_card", "gift_card_id": g["gift_id"], "amount": float(money(g["amount"]))}
                 for g in cur.fetchall()]
    return {"sale_id": ticket_id, "register": t["register_num"], "date": t["date"].isoformat(),
            "customer_id": t["customer_id"], "lines": lines, "subtotal": float(money(t["subtotal"])),
            "tax": float(money(t["tax"])), "total": float(money(t["total"])),
            "reward_points_earned": t["reward_points"], "payments": payments}


@APP.post("/sales", status_code=201)
def create_sale(inp: SaleIn):
    with transaction() as cur:
        session = open_session(cur, inp.register)
        if not session:
            raise fail(409, f"register {inp.register} is not open")
        require(cur, "employee", "SELECT employee_id FROM employee_info WHERE employee_id=%s", inp.employee_id)
        if inp.customer_id is not None:
            require(cur, "customer", "SELECT customer_id FROM customer_info WHERE customer_id=%s", inp.customer_id)

        wanted: dict[int, int] = {}
        for line in inp.lines:
            wanted[line.product_id] = wanted.get(line.product_id, 0) + line.qty
        products = {}
        for product_id in wanted:
            products[product_id] = require(cur, "product", "SELECT * FROM product_inventory WHERE product_id=%s"
                                           " FOR UPDATE", product_id)
        for product_id, qty in wanted.items():
            if products[product_id]["in_stock"] < qty:
                raise fail(409, f"not enough stock for product {product_id}")

        subtotal = sum((line.qty * money(products[line.product_id]["unit_price"]) for line in inp.lines), Decimal(0))
        subtotal = money(subtotal)
        rate = tax_rate(cur)
        tax = money(subtotal * rate)
        total = subtotal + tax
        paid = sum((money(p.amount) for p in inp.payments), Decimal(0))
        if paid != total:
            raise fail(422, f"payments add up to {paid}, but the total is {total}")
        for p in inp.payments:
            if p.method == "gift_card":
                if p.gift_card_id is None:
                    raise fail(422, "gift card payment without gift_card_id")
                card = require(cur, "gift card", "SELECT * FROM gift_card WHERE gift_id=%s FOR UPDATE", p.gift_card_id)
                if money(card["card_balance"]) < money(p.amount):
                    raise fail(409, f"gift card {p.gift_card_id} balance too low")

        points = int(total) if inp.customer_id is not None else 0
        at = now()
        cost = sum((line.qty * money(products[line.product_id]["cost"]) for line in inp.lines), Decimal(0))
        cash = sum((money(p.amount) for p in inp.payments if p.method == "cash"), Decimal(0))
        card = sum((money(p.amount) for p in inp.payments if p.method == "card"), Decimal(0))
        cur.execute("INSERT INTO ticket_system (date, company_name, time, quantity, subtotal, total, cost, tax,"
                    " tax_rate, cash, credit, cart_purchase, customer_id, employee_id, register_id, reward_points)"
                    " VALUES (%s,'Frischwerk',%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s)",
                    (at.date(), at.time(), sum(wanted.values()), float(subtotal), float(total), float(cost),
                     float(tax), float(rate), float(cash), float(card), inp.customer_id, inp.employee_id,
                     session["register_id"], points))
        ticket_id = cur.lastrowid
        cur.execute("INSERT INTO cart_inprogress (customer_id, ticket_id) VALUES (%s,%s)", (inp.customer_id, ticket_id))
        cid = cur.lastrowid
        for line in inp.lines:
            cur.execute("INSERT INTO item_list (CID, qty, product_id, unit_price) VALUES (%s,%s,%s,%s)",
                        (cid, line.qty, line.product_id, float(money(products[line.product_id]["unit_price"]))))
        for product_id, qty in wanted.items():
            cur.execute("UPDATE product_inventory SET in_stock = in_stock - %s WHERE product_id=%s", (qty, product_id))
        for p in inp.payments:
            if p.method == "gift_card":
                cur.execute("UPDATE gift_card SET card_balance = card_balance - %s, ticket_id=%s WHERE gift_id=%s",
                            (float(money(p.amount)), ticket_id, p.gift_card_id))
                cur.execute("INSERT INTO ticket_gift_payment (ticket_id, gift_id, amount) VALUES (%s,%s,%s)",
                            (ticket_id, p.gift_card_id, float(money(p.amount))))
        if points:
            cur.execute("UPDATE customer_info SET rewards = COALESCE(rewards,0) + %s WHERE customer_id=%s",
                        (points, inp.customer_id))
        return sale_body(cur, ticket_id)


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


@APP.post("/returns", status_code=201)
def create_return(inp: ReturnIn):
    with transaction() as cur:
        ticket = require(cur, "sale", "SELECT * FROM ticket_system WHERE ticket_id=%s FOR UPDATE", inp.sale_id)
        session = open_session(cur, inp.register)
        if not session:
            raise fail(409, f"register {inp.register} is not open")
        require(cur, "employee", "SELECT employee_id FROM employee_info WHERE employee_id=%s", inp.employee_id)
        cid = one(cur, "SELECT CID FROM cart_inprogress WHERE ticket_id=%s", inp.sale_id)["CID"]
        cur.execute("SELECT product_id, SUM(qty) AS qty, MAX(unit_price) AS unit_price FROM item_list"
                    " WHERE CID=%s GROUP BY product_id", (cid,))
        sold = {r["product_id"]: r for r in cur.fetchall()}
        cur.execute("SELECT i.product_id, SUM(i.qty) AS qty FROM return_items i JOIN return_table r ON r.RTID=i.RTID"
                    " WHERE r.ticket_id=%s GROUP BY i.product_id", (inp.sale_id,))
        returned = {r["product_id"]: int(r["qty"]) for r in cur.fetchall()}
        wanted: dict[int, int] = {}
        for line in inp.lines:
            wanted[line.product_id] = wanted.get(line.product_id, 0) + line.qty
        net = Decimal(0)
        for product_id, qty in wanted.items():
            if product_id not in sold:
                raise fail(409, f"product {product_id} is not part of sale {inp.sale_id}, cannot return it")
            if returned.get(product_id, 0) + qty > int(sold[product_id]["qty"]):
                raise fail(409, f"cannot return more of product {product_id} than was sold")
            net += qty * money(sold[product_id]["unit_price"])
        refund = money(net) + money(net * Decimal(str(ticket["tax_rate"])))
        at = now()
        cur.execute("INSERT INTO return_table (ticket_id, date, time, refunds, exchanges, register_id)"
                    " VALUES (%s,%s,%s,%s,0,%s)", (inp.sale_id, at.date(), at.time(), float(refund),
                                                   session["register_id"]))
        rtid = cur.lastrowid
        for product_id, qty in wanted.items():
            cur.execute("INSERT INTO return_items (RTID, product_id, qty) VALUES (%s,%s,%s)", (rtid, product_id, qty))
            cur.execute("UPDATE product_inventory SET in_stock = in_stock + %s WHERE product_id=%s", (qty, product_id))
        return {"return_id": rtid, "sale_id": inp.sale_id,
                "lines": [{"product_id": p, "qty": q} for p, q in wanted.items()],
                "refund_amount": float(refund)}


# --- purchasing ------------------------------------------------------------------------------

class OrderIn(BaseModel):
    vendor_id: int
    employee_id: int
    lines: list[Line] = Field(min_length=1)


class ReceiptIn(BaseModel):
    employee_id: int


def order_body(cur, otid: int) -> dict:
    o = require(cur, "purchase order", "SELECT * FROM orders_ticket WHERE OTID=%s", otid)
    cur.execute("SELECT product_id, stock_amount FROM orders WHERE OTID=%s ORDER BY OID", (otid,))
    lines = [{"product_id": r["product_id"], "qty": r["stock_amount"]} for r in cur.fetchall()]
    return {"purchase_order_id": otid, "vendor_id": o["vendor_id"], "status": "received" if o["status"] else "open",
            "lines": lines, "total_cost": float(money(o["total"]))}


@APP.post("/purchase-orders", status_code=201)
def create_order(inp: OrderIn):
    with transaction() as cur:
        require(cur, "vendor", "SELECT vendor_id FROM vendorinfo WHERE vendor_id=%s", inp.vendor_id)
        require(cur, "employee", "SELECT employee_id FROM employee_info WHERE employee_id=%s", inp.employee_id)
        total = Decimal(0)
        for line in inp.lines:
            p = require(cur, "product", "SELECT * FROM product_inventory WHERE product_id=%s", line.product_id)
            if p["vendor_id"] != inp.vendor_id:
                raise fail(422, f"product {line.product_id} is not supplied by vendor {inp.vendor_id}")
            total += line.qty * money(p["cost"])
        at = now()
        cur.execute("INSERT INTO orders_ticket (date, time, quantity, subtotal, total, status, employee_id, vendor_id)"
                    " VALUES (%s,%s,%s,%s,%s,0,%s,%s)", (at.date(), at.time(), sum(l.qty for l in inp.lines),
                                                        float(money(total)), float(money(total)),
                                                        inp.employee_id, inp.vendor_id))
        otid = cur.lastrowid
        for line in inp.lines:
            cur.execute("INSERT INTO orders (OTID, stock_amount, product_id) VALUES (%s,%s,%s)",
                        (otid, line.qty, line.product_id))
        return order_body(cur, otid)


@APP.get("/purchase-orders/{otid}")
def get_order(otid: int):
    with transaction() as cur:
        return order_body(cur, otid)


@APP.post("/purchase-orders/{otid}/receipt")
def receive_order(otid: int, inp: ReceiptIn):
    with transaction() as cur:
        o = require(cur, "purchase order", "SELECT * FROM orders_ticket WHERE OTID=%s FOR UPDATE", otid)
        require(cur, "employee", "SELECT employee_id FROM employee_info WHERE employee_id=%s", inp.employee_id)
        if o["status"]:
            raise fail(409, f"purchase order {otid} was already received")
        cur.execute("SELECT product_id, stock_amount FROM orders WHERE OTID=%s", (otid,))
        for r in cur.fetchall():
            cur.execute("UPDATE product_inventory SET in_stock = in_stock + %s WHERE product_id=%s",
                        (r["stock_amount"], r["product_id"]))
        cur.execute("UPDATE orders_ticket SET status=1 WHERE OTID=%s", (otid,))
        return order_body(cur, otid)


# --- sales report ------------------------------------------------------------------------------

@APP.get("/reports/sales")
def sales_report(store: int, to: date, from_: date = Query(alias="from")):
    with transaction() as cur:
        require(cur, "store", "SELECT SID FROM stores WHERE SID=%s", store)
        in_store = ("JOIN registers_table s ON s.register_id = {t}.register_id"
                    " JOIN store_registers sr ON sr.register_num = s.register_num AND sr.SID = %s")
        sales = one(cur, "SELECT COUNT(*) AS n, COALESCE(SUM(t.total),0) AS gross, COALESCE(SUM(t.tax),0) AS tax"
                         " FROM ticket_system t " + in_store.format(t="t") + " WHERE t.date BETWEEN %s AND %s",
                    store, from_, to)
        refunds = one(cur, "SELECT COALESCE(SUM(r.refunds),0) AS r FROM return_table r " + in_store.format(t="r")
                      + " WHERE r.date BETWEEN %s AND %s", store, from_, to)["r"]
        cur.execute("SELECT i.product_id, SUM(i.qty) AS qty FROM item_list i"
                    " JOIN cart_inprogress c ON c.CID = i.CID JOIN ticket_system t ON t.ticket_id = c.ticket_id "
                    + in_store.format(t="t") + " WHERE t.date BETWEEN %s AND %s"
                    " GROUP BY i.product_id ORDER BY qty DESC, i.product_id LIMIT 5", (store, from_, to))
        top = [{"product_id": r["product_id"], "qty": int(r["qty"])} for r in cur.fetchall()]
        gross, refunds = money(sales["gross"]), money(refunds)
        return {"store": store, "from": from_.isoformat(), "to": to.isoformat(), "sales_count": sales["n"],
                "gross_total": float(gross), "tax_total": float(money(sales["tax"])),
                "refunds_total": float(refunds), "net_revenue": float(gross - refunds), "top_products": top}

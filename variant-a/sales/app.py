"""sales (variant A): sales, returns, gift cards, the tax rate and the sales report.
Owns ticket_system, cart_inprogress, item_list, ticket_gift_payment,
return_table, return_items, gift_card and tax_table in sales-db."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import Query
from pydantic import BaseModel, Field

from common.calllog import Steps, call_ok, create_app, now
from common.db import fail, init_database, insert_rows, money, one, require, transaction

APP = create_app("sales")

SCHEMA = """
CREATE TABLE IF NOT EXISTS gift_card (
  gift_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  promo_number double NOT NULL, card_balance float NOT NULL,
  ticket_id int DEFAULT NULL, customer_id int DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS tax_table (
  TTID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  tax_year year NOT NULL, state_tax float NOT NULL, county_tax float NOT NULL,
  city_rate float NOT NULL, tax_rate float NOT NULL
);
CREATE TABLE IF NOT EXISTS ticket_system (
  ticket_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  date date NOT NULL, company_name varchar(50) DEFAULT NULL, time time NOT NULL,
  quantity int NOT NULL, subtotal float NOT NULL, total float NOT NULL, cost float NOT NULL,
  discount float DEFAULT NULL, tax float NOT NULL, tax_rate float NOT NULL,
  cash float NOT NULL, credit float NOT NULL, cart_purchase tinyint(1) NOT NULL,
  customer_id int DEFAULT NULL, employee_id int NOT NULL,
  register_id int NOT NULL,
  reward_points int NOT NULL DEFAULT 0,
  KEY register_id (register_id)
);
CREATE TABLE IF NOT EXISTS cart_inprogress (
  CID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  customer_id int DEFAULT NULL, ticket_id int DEFAULT NULL,
  KEY ticket_id (ticket_id)
);
CREATE TABLE IF NOT EXISTS item_list (
  ITID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  CID int NOT NULL, qty int NOT NULL, product_id int NOT NULL,
  unit_price float NOT NULL,
  KEY CID (CID)
);
CREATE TABLE IF NOT EXISTS ticket_gift_payment (
  ticket_id int NOT NULL, gift_id int NOT NULL, amount float NOT NULL,
  KEY ticket_id (ticket_id)
);
CREATE TABLE IF NOT EXISTS return_table (
  RTID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  ticket_id int NOT NULL, date date NOT NULL, time time NOT NULL,
  refunds float NOT NULL, exchanges float NOT NULL,
  register_id int NOT NULL,
  KEY ticket_id (ticket_id), KEY register_id (register_id)
);
CREATE TABLE IF NOT EXISTS return_items (
  RTID int NOT NULL, product_id int NOT NULL, qty int NOT NULL,
  KEY RTID (RTID)
);
"""


def fill(cur, seed: dict) -> None:
    insert_rows(cur, "gift_card", seed["gift_card"])
    insert_rows(cur, "tax_table", seed["tax_table"])


@APP.on_event("startup")
def startup():
    init_database(SCHEMA, fill, "tax_table")


def tax_rate(cur) -> Decimal:
    row = one(cur, "SELECT tax_rate FROM tax_table ORDER BY tax_year DESC LIMIT 1")
    return Decimal(str(row["tax_rate"]))


class Line(BaseModel):
    product_id: int
    qty: int = Field(ge=1)


def added_up(lines: list[Line]) -> dict[int, int]:
    wanted: dict[int, int] = {}
    for line in lines:
        wanted[line.product_id] = wanted.get(line.product_id, 0) + line.qty
    return wanted


def open_session(register: int) -> int:
    """Session id of the open session of the register (stores): 404 register, 409 register."""
    return call_ok("stores", "GET", f"/internal/registers/{register}/open-session")["session_id"]


def check_employee(employee_id: int) -> None:
    call_ok("people", "GET", f"/internal/employees/{employee_id}")


# --- gift cards ------------------------------------------------------------------------

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


def sale_body(cur, ticket_id: int, register: int | None = None) -> dict:
    """The sale as in the contract. Without 'register', stores is asked for the
    register of the sale's session."""
    t = require(cur, "sale", "SELECT * FROM ticket_system WHERE ticket_id=%s", ticket_id)
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
    if register is None:
        register = call_ok("stores", "GET", f"/internal/sessions/{t['register_id']}")["register"]
    return {"sale_id": ticket_id, "register": register, "date": t["date"].isoformat(),
            "customer_id": t["customer_id"], "lines": lines, "subtotal": float(money(t["subtotal"])),
            "tax": float(money(t["tax"])), "total": float(money(t["total"])),
            "reward_points_earned": t["reward_points"], "payments": payments}


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
    for gift_id in sorted(sums):
        card = require(cur, "gift card", "SELECT * FROM gift_card WHERE gift_id=%s" + (" FOR UPDATE" if lock else ""),
                       gift_id)
        if money(card["card_balance"]) < sums[gift_id]:
            raise fail(409, f"gift card {gift_id} balance too low")


@APP.post("/sales", status_code=201)
def create_sale(inp: SaleIn):
    # checks first, in the order of the monolith
    session_id = open_session(inp.register)
    check_employee(inp.employee_id)
    if inp.customer_id is not None:
        call_ok("people", "GET", f"/internal/customers/{inp.customer_id}")
    wanted = added_up(inp.lines)
    ids = ",".join(str(p) for p in wanted)
    products = {p["product_id"]: p for p in call_ok("inventory", "GET", "/internal/products", params={"ids": ids})}
    for product_id, qty in wanted.items():
        if products[product_id]["in_stock"] < qty:
            raise fail(409, f"not enough stock for product {product_id}")

    subtotal = money(sum((line.qty * money(products[line.product_id]["unit_price"]) for line in inp.lines),
                         Decimal(0)))
    with transaction() as cur:
        rate = tax_rate(cur)
    tax = money(subtotal * rate)
    total = subtotal + tax
    paid = sum((money(p.amount) for p in inp.payments), Decimal(0))
    if paid != total:
        raise fail(422, f"payments add up to {paid}, but the total is {total}")
    gift_sums = gift_card_sums(inp.payments)
    with transaction() as cur:
        check_gift_cards(cur, gift_sums, lock=False)

    points = int(total) if inp.customer_id is not None else 0
    lines = [{"product_id": p, "qty": q} for p, q in wanted.items()]
    with Steps() as steps:
        steps.run("inventory", "take_stock", "/internal/stock/take", {"lines": lines})
        if inp.customer_id is not None:
            steps.run("people", "add_points", f"/internal/customers/{inp.customer_id}/points", {"points": points})
        with transaction() as cur:
            check_gift_cards(cur, gift_sums, lock=True)  # checked again, rows locked
            at = now()
            cost = sum((line.qty * money(products[line.product_id]["cost"]) for line in inp.lines), Decimal(0))
            cash = sum((money(p.amount) for p in inp.payments if p.method == "cash"), Decimal(0))
            card = sum((money(p.amount) for p in inp.payments if p.method == "card"), Decimal(0))
            cur.execute("INSERT INTO ticket_system (date, company_name, time, quantity, subtotal, total, cost, tax,"
                        " tax_rate, cash, credit, cart_purchase, customer_id, employee_id, register_id, reward_points)"
                        " VALUES (%s,'Frischwerk',%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s)",
                        (at.date(), at.time(), sum(wanted.values()), float(subtotal), float(total), float(cost),
                         float(tax), float(rate), float(cash), float(card), inp.customer_id, inp.employee_id,
                         session_id, points))
            ticket_id = cur.lastrowid
            cur.execute("INSERT INTO cart_inprogress (customer_id, ticket_id) VALUES (%s,%s)",
                        (inp.customer_id, ticket_id))
            cid = cur.lastrowid
            for line in inp.lines:
                cur.execute("INSERT INTO item_list (CID, qty, product_id, unit_price) VALUES (%s,%s,%s,%s)",
                            (cid, line.qty, line.product_id, float(money(products[line.product_id]["unit_price"]))))
            for p in inp.payments:
                if p.method == "gift_card":
                    cur.execute("UPDATE gift_card SET card_balance = card_balance - %s, ticket_id=%s WHERE gift_id=%s",
                                (float(money(p.amount)), ticket_id, p.gift_card_id))
                    cur.execute("INSERT INTO ticket_gift_payment (ticket_id, gift_id, amount) VALUES (%s,%s,%s)",
                                (ticket_id, p.gift_card_id, float(money(p.amount))))
            return sale_body(cur, ticket_id, register=inp.register)


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
    """Lines are in the sale and not more than sold minus already returned
    (409 return). Answers the net amount of the returned lines."""
    cid = one(cur, "SELECT CID FROM cart_inprogress WHERE ticket_id=%s", sale_id)["CID"]
    cur.execute("SELECT product_id, SUM(qty) AS qty, MAX(unit_price) AS unit_price FROM item_list"
                " WHERE CID=%s GROUP BY product_id", (cid,))
    sold = {r["product_id"]: r for r in cur.fetchall()}
    cur.execute("SELECT i.product_id, SUM(i.qty) AS qty FROM return_items i JOIN return_table r ON r.RTID=i.RTID"
                " WHERE r.ticket_id=%s GROUP BY i.product_id", (sale_id,))
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
    with transaction() as cur:
        require(cur, "sale", "SELECT ticket_id FROM ticket_system WHERE ticket_id=%s", inp.sale_id)
    session_id = open_session(inp.register)
    check_employee(inp.employee_id)
    wanted = added_up(inp.lines)
    with transaction() as cur:
        check_return(cur, inp.sale_id, wanted)
    lines = [{"product_id": p, "qty": q} for p, q in wanted.items()]
    with Steps() as steps:
        steps.run("inventory", "give_stock_back", "/internal/stock/give-back", {"lines": lines})
        with transaction() as cur:
            ticket = one(cur, "SELECT * FROM ticket_system WHERE ticket_id=%s FOR UPDATE", inp.sale_id)
            net = check_return(cur, inp.sale_id, wanted)  # checked again, sale locked
            refund = money(net) + money(net * Decimal(str(ticket["tax_rate"])))
            at = now()
            cur.execute("INSERT INTO return_table (ticket_id, date, time, refunds, exchanges, register_id)"
                        " VALUES (%s,%s,%s,%s,0,%s)", (inp.sale_id, at.date(), at.time(), float(refund), session_id))
            rtid = cur.lastrowid
            for product_id, qty in wanted.items():
                cur.execute("INSERT INTO return_items (RTID, product_id, qty) VALUES (%s,%s,%s)",
                            (rtid, product_id, qty))
            return {"return_id": rtid, "sale_id": inp.sale_id, "lines": lines, "refund_amount": float(refund)}


# --- sales report ------------------------------------------------------------------------------

@APP.get("/reports/sales")
def sales_report(store: int, to: date, from_: date = Query(alias="from")):
    session_ids = call_ok("stores", "GET", f"/internal/stores/{store}/sessions")["session_ids"] or [0]
    marks = ",".join(["%s"] * len(session_ids))
    with transaction() as cur:
        sales = one(cur, "SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS gross, COALESCE(SUM(tax),0) AS tax"
                         f" FROM ticket_system WHERE register_id IN ({marks}) AND date BETWEEN %s AND %s",
                    *session_ids, from_, to)
        refunds = one(cur, "SELECT COALESCE(SUM(refunds),0) AS r FROM return_table"
                           f" WHERE register_id IN ({marks}) AND date BETWEEN %s AND %s",
                      *session_ids, from_, to)["r"]
        cur.execute("SELECT i.product_id, SUM(i.qty) AS qty FROM item_list i"
                    " JOIN cart_inprogress c ON c.CID = i.CID JOIN ticket_system t ON t.ticket_id = c.ticket_id"
                    f" WHERE t.register_id IN ({marks}) AND t.date BETWEEN %s AND %s"
                    " GROUP BY i.product_id ORDER BY qty DESC, i.product_id LIMIT 5", (*session_ids, from_, to))
        top = [{"product_id": r["product_id"], "qty": int(r["qty"])} for r in cur.fetchall()]
    gross, refunds = money(sales["gross"]), money(refunds)
    return {"store": store, "from": from_.isoformat(), "to": to.isoformat(), "sales_count": sales["n"],
            "gross_total": float(gross), "tax_total": float(money(sales["tax"])),
            "refunds_total": float(refunds), "net_revenue": float(gross - refunds), "top_products": top}


# --- internal calls ------------------------------------------------------------------

@APP.get("/internal/sessions/{session_id}/totals")
def session_totals(session_id: int):
    with transaction() as cur:
        sales = one(cur, "SELECT COUNT(*) AS n, COALESCE(SUM(total),0) AS gross, COALESCE(SUM(tax),0) AS tax,"
                         " COALESCE(SUM(cash),0) AS cash FROM ticket_system WHERE register_id=%s", session_id)
        refunds = one(cur, "SELECT COALESCE(SUM(refunds),0) AS r FROM return_table WHERE register_id=%s",
                      session_id)["r"]
    return {"session_id": session_id, "sales_count": sales["n"], "gross_total": float(money(sales["gross"])),
            "tax_total": float(money(sales["tax"])), "cash_sales": float(money(sales["cash"])),
            "refunds_total": float(money(refunds))}

"""inventory (variant A): products, stock, vendors and purchase orders.
Owns product_inventory, vendorinfo, orders_ticket and orders in inventory-db."""
from decimal import Decimal

from fastapi import Query
from pydantic import BaseModel, Field

from common.calllog import call_ok, create_app, now
from common.db import (APPLIED_STEPS, fail, finish_step, init_database, insert_rows, install_undo, money,
                       require, start_step, transaction)

APP = create_app("inventory")

SCHEMA = """
CREATE TABLE IF NOT EXISTS vendorinfo (
  vendor_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  company_name varchar(50) NOT NULL, department varchar(100) NOT NULL,
  street_address varchar(50) NOT NULL, city varchar(50) NOT NULL, state varchar(2) NOT NULL,
  zip_code int NOT NULL, phone_number double NOT NULL, fax_number double NOT NULL, email varchar(50) NOT NULL
);
CREATE TABLE IF NOT EXISTS product_inventory (
  product_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  brand varchar(50) NOT NULL, description varchar(50) NOT NULL, productName varchar(50) NOT NULL,
  productType varchar(50) NOT NULL, productSubType varchar(50) NOT NULL,
  unit_price float NOT NULL, cost float NOT NULL, in_stock int NOT NULL, vendor_id int NOT NULL
);
CREATE TABLE IF NOT EXISTS orders_ticket (
  OTID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  date date NOT NULL, time time NOT NULL, quantity int NOT NULL,
  subtotal float NOT NULL, total float NOT NULL, discount float DEFAULT NULL,
  tax float DEFAULT NULL, tax_rate float DEFAULT NULL, cash float DEFAULT NULL, credit float DEFAULT NULL,
  status int NOT NULL, employee_id int NOT NULL, vendor_id int NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  OID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  OTID int NOT NULL, stock_amount int NOT NULL, product_id int NOT NULL
);
""" + APPLIED_STEPS


def fill(cur, seed: dict) -> None:
    insert_rows(cur, "vendorinfo", seed["vendorinfo"])
    insert_rows(cur, "product_inventory", seed["product_inventory"])


@APP.on_event("startup")
def startup():
    init_database(SCHEMA, fill, "product_inventory")


class Line(BaseModel):
    product_id: int
    qty: int = Field(ge=1)


def added_up(lines: list[Line]) -> dict[int, int]:
    wanted: dict[int, int] = {}
    for line in lines:
        wanted[line.product_id] = wanted.get(line.product_id, 0) + line.qty
    return wanted


# --- products ------------------------------------------------------------------------

def product_body(p: dict) -> dict:
    return {"product_id": p["product_id"], "name": p["productName"], "brand": p["brand"],
            "category": p["productType"], "unit_price": float(money(p["unit_price"])),
            "cost": float(money(p["cost"])), "in_stock": p["in_stock"], "vendor_id": p["vendor_id"]}


@APP.get("/products/{product_id}")
def get_product(product_id: int):
    with transaction() as cur:
        return product_body(require(cur, "product", "SELECT * FROM product_inventory WHERE product_id=%s",
                                    product_id))


@APP.get("/internal/products")
def get_products(ids: str = Query(...)):
    try:
        wanted = [int(i) for i in ids.split(",") if i.strip()]
    except ValueError:
        raise fail(422, "ids must be integers") from None
    result = []
    with transaction() as cur:
        for product_id in wanted:
            p = require(cur, f"product {product_id}", "SELECT * FROM product_inventory WHERE product_id=%s",
                        product_id)
            result.append({"product_id": product_id, "unit_price": float(money(p["unit_price"])),
                           "cost": float(money(p["cost"])), "in_stock": p["in_stock"]})
    return result


# --- stock steps ---------------------------------------------------------------------

class StockIn(BaseModel):
    lines: list[Line] = Field(min_length=1)


def lines_body(changes: list[dict]) -> dict:
    return {"lines": changes}


@APP.post("/internal/stock/take")
def take_stock(inp: StockIn):
    """Step take_stock: all lines in one transaction, product rows locked."""
    wanted = added_up(inp.lines)
    with transaction() as cur:
        earlier = start_step(cur, "take_stock")
        if earlier is not None:
            return lines_body(earlier)
        for product_id in sorted(wanted):
            p = require(cur, f"product {product_id}",
                        "SELECT in_stock FROM product_inventory WHERE product_id=%s FOR UPDATE", product_id)
            if p["in_stock"] < wanted[product_id]:
                raise fail(409, f"not enough stock for product {product_id}")
        changes = [{"product_id": p, "qty": q} for p, q in wanted.items()]
        for line in changes:
            cur.execute("UPDATE product_inventory SET in_stock = in_stock - %s WHERE product_id=%s",
                        (line["qty"], line["product_id"]))
        finish_step(cur, "take_stock", changes)
        return lines_body(changes)


@APP.post("/internal/stock/give-back")
def give_stock_back(inp: StockIn):
    """Step give_stock_back."""
    wanted = added_up(inp.lines)
    with transaction() as cur:
        earlier = start_step(cur, "give_stock_back")
        if earlier is not None:
            return lines_body(earlier)
        for product_id in sorted(wanted):
            require(cur, f"product {product_id}",
                    "SELECT in_stock FROM product_inventory WHERE product_id=%s FOR UPDATE", product_id)
        changes = [{"product_id": p, "qty": q} for p, q in wanted.items()]
        for line in changes:
            cur.execute("UPDATE product_inventory SET in_stock = in_stock + %s WHERE product_id=%s",
                        (line["qty"], line["product_id"]))
        finish_step(cur, "give_stock_back", changes)
        return lines_body(changes)


def change_stock(sign: int):
    def reverse(cur, changes) -> None:
        for line in sorted(changes, key=lambda l: l["product_id"]):
            cur.execute("UPDATE product_inventory SET in_stock = in_stock + %s WHERE product_id=%s",
                        (sign * line["qty"], line["product_id"]))
    return reverse


install_undo(APP, {"take_stock": change_stock(+1), "give_stock_back": change_stock(-1)})


# --- purchase orders -----------------------------------------------------------------

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


def check_employee(employee_id: int) -> None:
    call_ok("people", "GET", f"/internal/employees/{employee_id}")


@APP.post("/purchase-orders", status_code=201)
def create_order(inp: OrderIn):
    with transaction() as cur:
        require(cur, "vendor", "SELECT vendor_id FROM vendorinfo WHERE vendor_id=%s", inp.vendor_id)
    check_employee(inp.employee_id)
    with transaction() as cur:
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
        require(cur, "purchase order", "SELECT OTID FROM orders_ticket WHERE OTID=%s", otid)
    check_employee(inp.employee_id)
    with transaction() as cur:
        o = require(cur, "purchase order", "SELECT * FROM orders_ticket WHERE OTID=%s FOR UPDATE", otid)
        if o["status"]:
            raise fail(409, f"purchase order {otid} was already received")
        cur.execute("SELECT product_id, stock_amount FROM orders WHERE OTID=%s ORDER BY product_id", (otid,))
        for r in cur.fetchall():
            cur.execute("UPDATE product_inventory SET in_stock = in_stock + %s WHERE product_id=%s",
                        (r["stock_amount"], r["product_id"]))
        cur.execute("UPDATE orders_ticket SET status=1 WHERE OTID=%s", (otid,))
        return order_body(cur, otid)

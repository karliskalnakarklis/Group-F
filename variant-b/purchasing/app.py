"""purchasing (variant B): assortment and purchasing.
Product master, suppliers, purchase orders and goods receipt, in
purchasing-db. Stock on hand is till's."""
from decimal import Decimal

from pydantic import BaseModel, Field

from common.calllog import Steps, call_ok, create_app, now
from common.db import fail, init_database, money, one, require, transaction

APP = create_app("purchasing")

SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  company_name varchar(50) NOT NULL, department varchar(100) NOT NULL DEFAULT '',
  street varchar(100) NOT NULL DEFAULT '', city varchar(50) NOT NULL DEFAULT '',
  zip_code varchar(10) NOT NULL DEFAULT '', phone varchar(30) NOT NULL DEFAULT '',
  fax varchar(30) NOT NULL DEFAULT '', email varchar(100) NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS products (
  product_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name varchar(50) NOT NULL, brand varchar(50) NOT NULL, description varchar(50) NOT NULL DEFAULT '',
  category varchar(50) NOT NULL, subcategory varchar(50) NOT NULL DEFAULT '',
  retail_price decimal(12,2) NOT NULL, cost decimal(12,2) NOT NULL, supplier_id int NOT NULL
);
CREATE TABLE IF NOT EXISTS staff (
  staff_id int NOT NULL PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS purchase_orders (
  purchase_order_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  supplier_id int NOT NULL, ordered_by int NOT NULL, ordered_at datetime NOT NULL,
  status varchar(10) NOT NULL, received_by int DEFAULT NULL, received_at datetime DEFAULT NULL,
  total_cost decimal(12,2) NOT NULL
);
CREATE TABLE IF NOT EXISTS order_lines (
  purchase_order_id int NOT NULL, line_no int NOT NULL, product_id int NOT NULL, qty int NOT NULL,
  PRIMARY KEY (purchase_order_id, line_no)
);
"""


def phone(value) -> str:
    return str(int(value)) if value else ""


def fill(cur, seed: dict) -> None:
    """Legacy vendorinfo -> suppliers, product_inventory -> products (without
    stock), employee_info -> staff IDs only."""
    for v in seed["vendorinfo"]:
        cur.execute("INSERT INTO suppliers (supplier_id, company_name, department, street, city, zip_code, phone,"
                    " fax, email) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (v["vendor_id"], v["company_name"], v["department"], v["street_address"], v["city"],
                     str(v["zip_code"]), phone(v["phone_number"]), phone(v["fax_number"]), v["email"]))
    for p in seed["product_inventory"]:
        cur.execute("INSERT INTO products (product_id, name, brand, description, category, subcategory,"
                    " retail_price, cost, supplier_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (p["product_id"], p["productName"], p["brand"], p["description"], p["productType"],
                     p["productSubType"], money(p["unit_price"]), money(p["cost"]), p["vendor_id"]))
    for e in seed["employee_info"]:
        cur.execute("INSERT INTO staff (staff_id) VALUES (%s)", (e["employee_id"],))


@APP.on_event("startup")
def startup():
    init_database(SCHEMA, fill, "products")


class Line(BaseModel):
    product_id: int
    qty: int = Field(ge=1)


def require_staff(cur, staff_id: int) -> None:
    require(cur, "employee", "SELECT staff_id FROM staff WHERE staff_id=%s", staff_id)


# --- products ------------------------------------------------------------------------

@APP.get("/products/{product_id}")
def get_product(product_id: int):
    with transaction() as cur:
        p = require(cur, "product", "SELECT * FROM products WHERE product_id=%s", product_id)
    on_hand = call_ok("till", "GET", f"/internal/stock/{product_id}")["on_hand"]
    return {"product_id": p["product_id"], "name": p["name"], "brand": p["brand"], "category": p["category"],
            "unit_price": float(money(p["retail_price"])), "cost": float(money(p["cost"])),
            "in_stock": on_hand, "vendor_id": p["supplier_id"]}


@APP.get("/internal/price-list")
def price_list():
    with transaction() as cur:
        cur.execute("SELECT product_id, retail_price, category FROM products ORDER BY product_id")
        return [{"product_id": r["product_id"], "unit_price": float(money(r["retail_price"])),
                 "category": r["category"]}
                for r in cur.fetchall()]


# --- purchase orders -----------------------------------------------------------------

class OrderIn(BaseModel):
    vendor_id: int
    employee_id: int
    lines: list[Line] = Field(min_length=1)


class ReceiptIn(BaseModel):
    employee_id: int


def order_body(cur, order_id: int) -> dict:
    o = require(cur, "purchase order", "SELECT * FROM purchase_orders WHERE purchase_order_id=%s", order_id)
    cur.execute("SELECT product_id, qty FROM order_lines WHERE purchase_order_id=%s ORDER BY line_no", (order_id,))
    lines = [{"product_id": r["product_id"], "qty": r["qty"]} for r in cur.fetchall()]
    return {"purchase_order_id": order_id, "vendor_id": o["supplier_id"], "status": o["status"],
            "lines": lines, "total_cost": float(money(o["total_cost"]))}


@APP.post("/purchase-orders", status_code=201)
def create_order(inp: OrderIn):
    with transaction() as cur:
        require(cur, "vendor", "SELECT supplier_id FROM suppliers WHERE supplier_id=%s", inp.vendor_id)
        require_staff(cur, inp.employee_id)
        total = Decimal(0)
        for line in inp.lines:
            p = require(cur, "product", "SELECT * FROM products WHERE product_id=%s", line.product_id)
            if p["supplier_id"] != inp.vendor_id:
                raise fail(422, f"product {line.product_id} is not supplied by vendor {inp.vendor_id}")
            total += line.qty * money(p["cost"])
        cur.execute("INSERT INTO purchase_orders (supplier_id, ordered_by, ordered_at, status, total_cost)"
                    " VALUES (%s,%s,%s,'open',%s)",
                    (inp.vendor_id, inp.employee_id, now().replace(tzinfo=None), money(total)))
        order_id = cur.lastrowid
        for n, line in enumerate(inp.lines, start=1):
            cur.execute("INSERT INTO order_lines (purchase_order_id, line_no, product_id, qty) VALUES (%s,%s,%s,%s)",
                        (order_id, n, line.product_id, line.qty))
        return order_body(cur, order_id)


@APP.get("/purchase-orders/{order_id}")
def get_order(order_id: int):
    with transaction() as cur:
        return order_body(cur, order_id)


@APP.post("/purchase-orders/{order_id}/receipt")
def receive_order(order_id: int, inp: ReceiptIn):
    with transaction() as cur:
        o = require(cur, "purchase order", "SELECT * FROM purchase_orders WHERE purchase_order_id=%s", order_id)
        require_staff(cur, inp.employee_id)
        if o["status"] == "received":
            raise fail(409, f"purchase order {order_id} was already received")
        cur.execute("SELECT product_id, qty FROM order_lines WHERE purchase_order_id=%s ORDER BY line_no",
                    (order_id,))
        lines = [{"product_id": r["product_id"], "qty": r["qty"]} for r in cur.fetchall()]
    with Steps() as steps:
        steps.run("till", "receive_stock", "/internal/stock/receive", {"lines": lines})
        with transaction() as cur:
            o = one(cur, "SELECT * FROM purchase_orders WHERE purchase_order_id=%s FOR UPDATE", order_id)
            if o["status"] == "received":  # another receipt was faster
                raise fail(409, f"purchase order {order_id} was already received")
            cur.execute("UPDATE purchase_orders SET status='received', received_by=%s, received_at=%s"
                        " WHERE purchase_order_id=%s", (inp.employee_id, now().replace(tzinfo=None), order_id))
            return order_body(cur, order_id)

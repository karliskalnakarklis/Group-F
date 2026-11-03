"""purchasing: assortment and purchasing (variant B). Product master, suppliers,
purchase orders, goods receipt. Stock on hand is till's: the product lookup asks
till for it, the goods receipt adds it in till (step receive_stock)."""
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from common import calllog, seed
from common.client import call, expect, undo
from common.db import create_schema, one, require, schema_file, transaction, wait_for_db
from common.money import money, now

SERVICE = "purchasing"

calllog.init(SERVICE)
APP = FastAPI(title="purchasing")
APP.add_middleware(calllog.CallLog)


def fail(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def digits(value) -> str:
    return str(int(value)) if isinstance(value, (int, float)) else str(value)


def fill_from_seed(cur, data: dict) -> None:
    for v in data["vendorinfo"]:
        cur.execute("INSERT INTO suppliers (supplier_id, company_name, department, street, zip_code, city, phone, fax,"
                    " email) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (v["vendor_id"], v["company_name"], v["department"], v["street_address"], digits(v["zip_code"]),
                     v["city"], digits(v["phone_number"]), digits(v["fax_number"]), v["email"]))
    for p in data["product_inventory"]:
        cur.execute("INSERT INTO products (product_id, name, brand, description, category, subcategory, retail_price,"
                    " cost, supplier_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (p["product_id"], p["productName"], p["brand"], p["description"], p["productType"],
                     p["productSubType"], str(money(p["unit_price"])), str(money(p["cost"])), p["vendor_id"]))
    for e in data["employee_info"]:
        cur.execute("INSERT INTO staff (staff_id) VALUES (%s)", (e["employee_id"],))


@APP.on_event("startup")
def start():
    wait_for_db()
    create_schema(schema_file(__file__))
    seed.load_once("products", fill_from_seed)


@APP.get("/health")
def health():
    return {"status": "ok"}


# --- products -----------------------------------------------------------------------------

@APP.get("/products/{product_id}")
def get_product(product_id: int):
    with transaction() as cur:
        p = require(cur, "product", "SELECT * FROM products WHERE product_id=%s", product_id)
    on_hand = expect(call("till", "GET", f"/internal/stock/{product_id}"))["on_hand"]
    return {"product_id": p["product_id"], "name": p["name"], "brand": p["brand"], "category": p["category"],
            "unit_price": float(money(p["retail_price"])), "cost": float(money(p["cost"])), "in_stock": on_hand,
            "vendor_id": p["supplier_id"]}


@APP.get("/internal/price-list")
def price_list():
    with transaction() as cur:
        cur.execute("SELECT product_id, retail_price, category FROM products ORDER BY product_id")
        return [{"product_id": r["product_id"], "unit_price": float(money(r["retail_price"])), "category": r["category"]}
                for r in cur.fetchall()]


# --- purchase orders and goods receipt ------------------------------------------------------------

class Line(BaseModel):
    product_id: int
    qty: int = Field(ge=1)


class OrderIn(BaseModel):
    vendor_id: int
    employee_id: int
    lines: list[Line] = Field(min_length=1)


class ReceiptIn(BaseModel):
    employee_id: int


def order_body(cur, purchase_order_id: int) -> dict:
    o = require(cur, "purchase order", "SELECT * FROM purchase_orders WHERE purchase_order_id=%s", purchase_order_id)
    cur.execute("SELECT product_id, qty FROM order_lines WHERE purchase_order_id=%s ORDER BY line_no",
                (purchase_order_id,))
    return {"purchase_order_id": purchase_order_id, "vendor_id": o["supplier_id"], "status": o["status"],
            "lines": [{"product_id": r["product_id"], "qty": r["qty"]} for r in cur.fetchall()],
            "total_cost": float(money(o["total_cost"]))}


@APP.post("/purchase-orders", status_code=201)
def create_order(inp: OrderIn):
    with transaction() as cur:
        require(cur, "vendor", "SELECT supplier_id FROM suppliers WHERE supplier_id=%s", inp.vendor_id)
        require(cur, "employee", "SELECT staff_id FROM staff WHERE staff_id=%s", inp.employee_id)
        total = Decimal(0)
        for line in inp.lines:
            p = require(cur, "product", "SELECT supplier_id, cost FROM products WHERE product_id=%s", line.product_id)
            if p["supplier_id"] != inp.vendor_id:
                raise fail(422, f"product {line.product_id} is not supplied by vendor {inp.vendor_id}")
            total += line.qty * money(p["cost"])
        cur.execute("INSERT INTO purchase_orders (supplier_id, ordered_by, ordered_at, total_cost, status)"
                    " VALUES (%s,%s,%s,%s,'open')", (inp.vendor_id, inp.employee_id, now().replace(tzinfo=None),
                                                     str(money(total))))
        purchase_order_id = cur.lastrowid
        for n, line in enumerate(inp.lines, 1):
            cur.execute("INSERT INTO order_lines (purchase_order_id, line_no, product_id, qty) VALUES (%s,%s,%s,%s)",
                        (purchase_order_id, n, line.product_id, line.qty))
        return order_body(cur, purchase_order_id)


@APP.get("/purchase-orders/{purchase_order_id}")
def get_order(purchase_order_id: int):
    with transaction() as cur:
        return order_body(cur, purchase_order_id)


@APP.post("/purchase-orders/{purchase_order_id}/receipt")
def receive_order(purchase_order_id: int, inp: ReceiptIn):
    with transaction() as cur:
        o = require(cur, "purchase order", "SELECT * FROM purchase_orders WHERE purchase_order_id=%s",
                    purchase_order_id)
        require(cur, "employee", "SELECT staff_id FROM staff WHERE staff_id=%s", inp.employee_id)
        if o["status"] == "received":
            raise fail(409, f"purchase order {purchase_order_id} was already received")
        lines = order_body(cur, purchase_order_id)["lines"]

    try:
        expect(call("till", "POST", "/internal/stock/receive", {"lines": lines}))
    except HTTPException:
        undo("till", "receive_stock")
        raise

    try:
        with transaction() as cur:
            o = one(cur, "SELECT status FROM purchase_orders WHERE purchase_order_id=%s FOR UPDATE", purchase_order_id)
            if o["status"] == "received":
                raise fail(409, f"purchase order {purchase_order_id} was already received")
            cur.execute("UPDATE purchase_orders SET status='received', received_by=%s, received_at=%s"
                        " WHERE purchase_order_id=%s", (inp.employee_id, now().replace(tzinfo=None), purchase_order_id))
            return order_body(cur, purchase_order_id)
    except BaseException:
        undo("till", "receive_stock")
        raise

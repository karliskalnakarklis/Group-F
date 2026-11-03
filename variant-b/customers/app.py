"""customers: customers and loyalty (variant B). Customer profiles and reward
points, tiers by 12-month spend (CR2). The loyalty rule lives here: till only
reports the total and date of a sale."""
import math
from datetime import date, timedelta
from decimal import Decimal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from common import calllog, seed
from common.db import create_schema, one, require, schema_file, transaction, wait_for_db
from common.money import money, now
from common.receipts import SCHEMA as RECEIPTS, router as undo_router, run_step, undo_handler

SERVICE = "customers"
TIERS = [(Decimal(2000), "gold", 3), (Decimal(500), "silver", 2), (Decimal(0), "bronze", 1)]  # CR2

calllog.init(SERVICE)
APP = FastAPI(title="customers")
APP.add_middleware(calllog.CallLog)
APP.include_router(undo_router)


def digits(value) -> str:
    return str(int(value)) if isinstance(value, (int, float)) else str(value)


def fill_from_seed(cur, data: dict) -> None:
    for c in data["customer_info"]:
        cur.execute("INSERT INTO customers (customer_id, first_name, last_name, email, phone, street, zip_code, city,"
                    " reward_points) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (c["customer_id"], c["first_name"], c["last_name"], c["email"], digits(c["phone_number"]),
                     c["street_address"], digits(c["zip_code"]), c["city"], int(c["rewards"] or 0)))


@APP.on_event("startup")
def start():
    wait_for_db()
    create_schema(schema_file(__file__), RECEIPTS)
    seed.load_once("customers", fill_from_seed)


@APP.get("/health")
def health():
    return {"status": "ok"}


class CustomerIn(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    street: str = ""
    zip_code: int | str = ""
    city: str = ""


def spend_12m(cur, customer_id: int, today: date) -> Decimal:
    """CR2: totals of the sales of today and the 364 days before, minus the refunds of those sales."""
    row = one(cur, "SELECT COALESCE(SUM(IF(kind='earn', amount, -amount)),0) AS spend FROM point_movements"
                   " WHERE customer_id=%s AND sale_date BETWEEN %s AND %s",
              customer_id, today - timedelta(days=364), today)
    return money(row["spend"])


def tier_of(spend: Decimal) -> tuple[str, int]:
    return next((name, points) for limit, name, points in TIERS if spend >= limit)


def customer_body(cur, c: dict) -> dict:
    spend = spend_12m(cur, c["customer_id"], now().date())
    return {"customer_id": c["customer_id"], "first_name": c["first_name"], "last_name": c["last_name"],
            "email": c["email"], "reward_points": c["reward_points"], "tier": tier_of(spend)[0],
            "spend_12m": float(spend)}


def find(cur, customer_id: int, lock: bool = False) -> dict:
    return require(cur, "customer", "SELECT * FROM customers WHERE customer_id=%s" + (" FOR UPDATE" if lock else ""),
                   customer_id)


@APP.post("/customers", status_code=201)
def register_customer(inp: CustomerIn):
    with transaction() as cur:
        cur.execute("INSERT INTO customers (first_name, last_name, email, phone, street, zip_code, city, reward_points)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,0)", (inp.first_name, inp.last_name, inp.email, inp.phone,
                                                         inp.street, str(inp.zip_code), inp.city))
        return customer_body(cur, find(cur, cur.lastrowid))


@APP.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    with transaction() as cur:
        return customer_body(cur, find(cur, customer_id))


# --- internal: points for a sale (step earn_points) ----------------------------------------------

class EarnIn(BaseModel):
    total: float = Field(ge=0)
    date: date


class RefundIn(BaseModel):
    sale_date: date
    refund_amount: float = Field(ge=0)
    points_per_chf: int = Field(ge=0)


@APP.post("/internal/customers/{customer_id}/earn")
def earn(customer_id: int, inp: EarnIn):
    def apply(cur):
        find(cur, customer_id, lock=True)
        tier, points_per_chf = tier_of(spend_12m(cur, customer_id, inp.date))  # the tier before the sale
        points = math.floor(money(inp.total)) * points_per_chf
        cur.execute("UPDATE customers SET reward_points = reward_points + %s WHERE customer_id=%s",
                    (points, customer_id))
        cur.execute("INSERT INTO point_movements (customer_id, kind, sale_date, amount) VALUES (%s,'earn',%s,%s)",
                    (customer_id, inp.date, str(money(inp.total))))
        return {"customer_id": customer_id, "points": points, "movement_id": cur.lastrowid, "tier": tier,
                "points_per_chf": points_per_chf}

    def answer(cur, changes):
        c = find(cur, changes["customer_id"])
        return {"customer_id": c["customer_id"], "points_earned": changes["points"],
                "reward_points": c["reward_points"], "tier": changes["tier"],
                "points_per_chf": changes["points_per_chf"]}

    return run_step("earn_points", apply, answer)


@undo_handler("earn_points")
def undo_earn(cur, changes):
    cur.execute("UPDATE customers SET reward_points = reward_points - %s WHERE customer_id=%s",
                (changes["points"], changes["customer_id"]))
    cur.execute("DELETE FROM point_movements WHERE movement_id=%s", (changes["movement_id"],))


# --- internal: points taken back by a return (step refund_points, CR2) ------------------------------

@APP.post("/internal/customers/{customer_id}/refund")
def refund(customer_id: int, inp: RefundIn):
    def apply(cur):
        c = find(cur, customer_id, lock=True)
        removed = min(c["reward_points"], math.floor(money(inp.refund_amount)) * inp.points_per_chf)  # never below 0
        cur.execute("UPDATE customers SET reward_points = reward_points - %s WHERE customer_id=%s",
                    (removed, customer_id))
        cur.execute("INSERT INTO point_movements (customer_id, kind, sale_date, amount) VALUES (%s,'refund',%s,%s)",
                    (customer_id, inp.sale_date, str(money(inp.refund_amount))))
        return {"customer_id": customer_id, "points_removed": removed, "movement_id": cur.lastrowid}

    def answer(cur, changes):
        c = find(cur, changes["customer_id"])
        return {"customer_id": c["customer_id"], "points_removed": changes["points_removed"],
                "reward_points": c["reward_points"]}

    return run_step("refund_points", apply, answer)


@undo_handler("refund_points")
def undo_refund(cur, changes):
    cur.execute("UPDATE customers SET reward_points = reward_points + %s WHERE customer_id=%s",
                (changes["points_removed"], changes["customer_id"]))
    cur.execute("DELETE FROM point_movements WHERE movement_id=%s", (changes["movement_id"],))

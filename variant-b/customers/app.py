"""customers (variant B): customers and loyalty.
Customer profiles and reward points, in customers-db. The only service with
personal data of customers."""
import math
from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel, Field

from common.calllog import create_app, now
from common.db import (APPLIED_STEPS, finish_step, init_database, install_undo, money, one, require, start_step,
                       transaction)

APP = create_app("customers")

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  customer_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  first_name varchar(50) NOT NULL, last_name varchar(50) NOT NULL,
  email varchar(100) NOT NULL, phone varchar(30) NOT NULL DEFAULT '',
  street varchar(100) NOT NULL DEFAULT '', zip_code varchar(10) NOT NULL DEFAULT '',
  city varchar(50) NOT NULL DEFAULT '', reward_points int NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS spend_entries (
  entry_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  customer_id int NOT NULL, sale_date date NOT NULL, amount decimal(12,2) NOT NULL,
  KEY customer_day (customer_id, sale_date)
);
""" + APPLIED_STEPS


def fill(cur, seed: dict) -> None:
    """Legacy customer_info -> customers. The legacy password and US state are dropped."""
    for c in seed["customer_info"]:
        cur.execute("INSERT INTO customers (customer_id, first_name, last_name, email, phone, street, zip_code,"
                    " city, reward_points) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (c["customer_id"], c["first_name"], c["last_name"], c["email"],
                     str(int(c["phone_number"])) if c["phone_number"] else "", c["street_address"],
                     str(c["zip_code"]), c["city"], int(c["rewards"] or 0)))


@APP.on_event("startup")
def startup():
    init_database(SCHEMA, fill, "customers")


# --- contract endpoints ------------------------------------------------------------

class CustomerIn(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    street: str = ""
    zip_code: int | str = ""
    city: str = ""


def customer_body(cur, c: dict) -> dict:
    spend = spend_12m(cur, c["customer_id"], now().date())
    return {"customer_id": c["customer_id"], "first_name": c["first_name"], "last_name": c["last_name"],
            "email": c["email"], "reward_points": c["reward_points"], "tier": tier_of(spend),
            "spend_12m": float(spend)}


@APP.post("/customers", status_code=201)
def register_customer(inp: CustomerIn):
    with transaction() as cur:
        cur.execute("INSERT INTO customers (first_name, last_name, email, phone, street, zip_code, city,"
                    " reward_points) VALUES (%s,%s,%s,%s,%s,%s,%s,0)",
                    (inp.first_name, inp.last_name, inp.email, inp.phone, inp.street, str(inp.zip_code), inp.city))
        return customer_body(cur, one(cur, "SELECT * FROM customers WHERE customer_id=%s", cur.lastrowid))


@APP.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    with transaction() as cur:
        return customer_body(cur, require(cur, "customer", "SELECT * FROM customers WHERE customer_id=%s",
                                          customer_id))


# --- loyalty tiers (CR2) -------------------------------------------------------------

POINTS_PER_CHF = {"bronze": 1, "silver": 2, "gold": 3}


def spend_12m(cur, customer_id: int, today: date) -> Decimal:
    """Sum of the spend entries with a sale date in [today - 364 days, today]."""
    row = one(cur, "SELECT COALESCE(SUM(amount),0) AS spend FROM spend_entries"
                   " WHERE customer_id=%s AND sale_date BETWEEN %s AND %s",
              customer_id, today - timedelta(days=364), today)
    return money(row["spend"])


def tier_of(spend: Decimal) -> str:
    if spend >= 2000:
        return "gold"
    return "silver" if spend >= 500 else "bronze"


def add_spend(cur, customer_id: int, sale_date: date, amount: Decimal) -> int:
    cur.execute("INSERT INTO spend_entries (customer_id, sale_date, amount) VALUES (%s,%s,%s)",
                (customer_id, sale_date, amount))
    return cur.lastrowid


# --- internal calls ------------------------------------------------------------------

class EarnIn(BaseModel):
    total: Decimal = Field(ge=0)
    sale_date: date


class TakeBackIn(BaseModel):
    refund_amount: Decimal = Field(ge=0)
    tier: str | None = Field(default=None, pattern="^(bronze|silver|gold)$")  # None: a sale from version 1
    sale_date: date


@APP.post("/internal/customers/{customer_id}/earn")
def earn_points(customer_id: int, inp: EarnIn):
    """Step earn_points. The loyalty rule (CR2): the tier from the spend before
    this sale, points_earned = floor(total) x points per CHF of the tier."""
    with transaction() as cur:
        earlier = start_step(cur, "earn_points")
        customer = require(cur, "customer", "SELECT * FROM customers WHERE customer_id=%s FOR UPDATE", customer_id)
        if earlier is not None:
            points, tier = earlier["points"], earlier["tier"]
        else:
            tier = tier_of(spend_12m(cur, customer_id, inp.sale_date))
            points = math.floor(inp.total) * POINTS_PER_CHF[tier]
            cur.execute("UPDATE customers SET reward_points = reward_points + %s WHERE customer_id=%s",
                        (points, customer_id))
            entry_id = add_spend(cur, customer_id, inp.sale_date, money(inp.total))
            finish_step(cur, "earn_points", {"customer_id": customer_id, "points": points, "tier": tier,
                                             "spend_entry_id": entry_id})
            customer = one(cur, "SELECT * FROM customers WHERE customer_id=%s", customer_id)
        return {"customer_id": customer_id, "tier": tier, "points_earned": points,
                "reward_points": customer["reward_points"]}


@APP.post("/internal/customers/{customer_id}/take-back")
def take_back_points(customer_id: int, inp: TakeBackIn):
    """Step take_back_points (CR2): subtract floor(refund_amount) x points per
    CHF of the sale's tier, never below 0, and add -refund_amount to the spend
    at the date of the sale."""
    with transaction() as cur:
        earlier = start_step(cur, "take_back_points")
        customer = require(cur, "customer", "SELECT * FROM customers WHERE customer_id=%s FOR UPDATE", customer_id)
        if earlier is not None:
            points = earlier["points"]
        else:
            # a sale from version 1 earned 1 point per CHF and has no spend entry, so its return adds none
            rate = POINTS_PER_CHF[inp.tier] if inp.tier else 1
            points = min(customer["reward_points"], math.floor(inp.refund_amount) * rate)
            cur.execute("UPDATE customers SET reward_points = reward_points - %s WHERE customer_id=%s",
                        (points, customer_id))
            entry_id = add_spend(cur, customer_id, inp.sale_date, -money(inp.refund_amount)) if inp.tier else None
            finish_step(cur, "take_back_points", {"customer_id": customer_id, "points": points,
                                                  "spend_entry_id": entry_id})
            customer = one(cur, "SELECT * FROM customers WHERE customer_id=%s", customer_id)
        return {"customer_id": customer_id, "points_taken_back": points, "reward_points": customer["reward_points"]}


def reverse_earn(cur, changes) -> None:
    if changes:
        cur.execute("UPDATE customers SET reward_points = reward_points - %s WHERE customer_id=%s",
                    (changes["points"], changes["customer_id"]))
        cur.execute("DELETE FROM spend_entries WHERE entry_id=%s", (changes["spend_entry_id"],))


def reverse_take_back(cur, changes) -> None:
    if changes:
        cur.execute("UPDATE customers SET reward_points = reward_points + %s WHERE customer_id=%s",
                    (changes["points"], changes["customer_id"]))
        if changes["spend_entry_id"] is not None:
            cur.execute("DELETE FROM spend_entries WHERE entry_id=%s", (changes["spend_entry_id"],))


install_undo(APP, {"earn_points": reverse_earn, "take_back_points": reverse_take_back})

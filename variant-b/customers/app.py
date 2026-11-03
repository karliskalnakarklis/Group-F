"""customers (variant B): customers and loyalty.
Customer profiles and reward points, in customers-db. The only service with
personal data of customers."""
import math
from decimal import Decimal

from pydantic import BaseModel, Field

from common.calllog import create_app
from common.db import APPLIED_STEPS, finish_step, init_database, install_undo, one, require, start_step, transaction

APP = create_app("customers")

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  customer_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  first_name varchar(50) NOT NULL, last_name varchar(50) NOT NULL,
  email varchar(100) NOT NULL, phone varchar(30) NOT NULL DEFAULT '',
  street varchar(100) NOT NULL DEFAULT '', zip_code varchar(10) NOT NULL DEFAULT '',
  city varchar(50) NOT NULL DEFAULT '', reward_points int NOT NULL DEFAULT 0
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


def customer_body(c: dict) -> dict:
    return {"customer_id": c["customer_id"], "first_name": c["first_name"], "last_name": c["last_name"],
            "email": c["email"], "reward_points": c["reward_points"]}


@APP.post("/customers", status_code=201)
def register_customer(inp: CustomerIn):
    with transaction() as cur:
        cur.execute("INSERT INTO customers (first_name, last_name, email, phone, street, zip_code, city,"
                    " reward_points) VALUES (%s,%s,%s,%s,%s,%s,%s,0)",
                    (inp.first_name, inp.last_name, inp.email, inp.phone, inp.street, str(inp.zip_code), inp.city))
        return customer_body(one(cur, "SELECT * FROM customers WHERE customer_id=%s", cur.lastrowid))


@APP.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    with transaction() as cur:
        return customer_body(require(cur, "customer", "SELECT * FROM customers WHERE customer_id=%s", customer_id))


# --- internal calls ------------------------------------------------------------------

class EarnIn(BaseModel):
    total: Decimal = Field(ge=0)


@APP.post("/internal/customers/{customer_id}/earn")
def earn_points(customer_id: int, inp: EarnIn):
    """Step earn_points. The loyalty rule: points_earned = floor(total)."""
    with transaction() as cur:
        earlier = start_step(cur, "earn_points")
        customer = require(cur, "customer", "SELECT * FROM customers WHERE customer_id=%s FOR UPDATE", customer_id)
        if earlier is not None:
            points = earlier["points"]
        else:
            points = math.floor(inp.total)
            cur.execute("UPDATE customers SET reward_points = reward_points + %s WHERE customer_id=%s",
                        (points, customer_id))
            finish_step(cur, "earn_points", {"customer_id": customer_id, "points": points})
            customer = one(cur, "SELECT * FROM customers WHERE customer_id=%s", customer_id)
        return {"customer_id": customer_id, "points_earned": points, "reward_points": customer["reward_points"]}


def reverse_earn(cur, changes) -> None:
    if changes:
        cur.execute("UPDATE customers SET reward_points = reward_points - %s WHERE customer_id=%s",
                    (changes["points"], changes["customer_id"]))


install_undo(APP, {"earn_points": reverse_earn})

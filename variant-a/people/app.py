"""people (variant A): customers and employees.
Owns customer_info and employee_info in people-db."""
from pydantic import BaseModel, Field

from common.calllog import create_app
from common.db import (APPLIED_STEPS, finish_step, init_database, insert_rows, install_undo, one, require,
                       start_step, transaction)

APP = create_app("people")

SCHEMA = """
CREATE TABLE IF NOT EXISTS customer_info (
  customer_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email varchar(50) NOT NULL, password varchar(60) NOT NULL,
  first_name varchar(50) NOT NULL, last_name varchar(50) NOT NULL,
  phone_number double NOT NULL, rewards float DEFAULT NULL,
  street_address varchar(50) NOT NULL, city varchar(50) NOT NULL,
  state varchar(2) NOT NULL, zip_code int NOT NULL
);
CREATE TABLE IF NOT EXISTS employee_info (
  employee_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  email varchar(50) NOT NULL, password varchar(50) NOT NULL, pin_number int NOT NULL,
  first_name varchar(50) NOT NULL, last_name varchar(50) NOT NULL, user_id double NOT NULL,
  phone_number double NOT NULL, SSN double NOT NULL, street_address varchar(50) NOT NULL,
  city varchar(50) NOT NULL, state varchar(2) NOT NULL, zip_code int NOT NULL,
  start_date date NOT NULL, company_name varchar(50) NOT NULL, number_of_stores varchar(11) DEFAULT NULL,
  user_type int NOT NULL, customer_id int DEFAULT NULL
);
""" + APPLIED_STEPS


def fill(cur, seed: dict) -> None:
    insert_rows(cur, "customer_info", seed["customer_info"])
    insert_rows(cur, "employee_info", seed["employee_info"])


@APP.on_event("startup")
def startup():
    init_database(SCHEMA, fill, "employee_info")


# --- contract endpoints ------------------------------------------------------------

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
        return customer_body(require(cur, "customer", "SELECT * FROM customer_info WHERE customer_id=%s",
                                     customer_id))


# --- internal calls ------------------------------------------------------------------

@APP.get("/internal/employees/{employee_id}")
def employee_exists(employee_id: int):
    with transaction() as cur:
        require(cur, "employee", "SELECT employee_id FROM employee_info WHERE employee_id=%s", employee_id)
    return {"employee_id": employee_id}


@APP.get("/internal/customers/{customer_id}")
def customer_exists(customer_id: int):
    with transaction() as cur:
        require(cur, "customer", "SELECT customer_id FROM customer_info WHERE customer_id=%s", customer_id)
    return {"customer_id": customer_id}


class PointsIn(BaseModel):
    points: int = Field(ge=0)


@APP.post("/internal/customers/{customer_id}/points")
def add_points(customer_id: int, inp: PointsIn):
    """Step add_points."""
    with transaction() as cur:
        earlier = start_step(cur, "add_points")
        customer = require(cur, "customer", "SELECT * FROM customer_info WHERE customer_id=%s FOR UPDATE",
                           customer_id)
        if earlier is None:
            cur.execute("UPDATE customer_info SET rewards = COALESCE(rewards,0) + %s WHERE customer_id=%s",
                        (inp.points, customer_id))
            finish_step(cur, "add_points", {"customer_id": customer_id, "points": inp.points})
            customer = one(cur, "SELECT * FROM customer_info WHERE customer_id=%s", customer_id)
        return {"customer_id": customer_id, "reward_points": int(customer["rewards"] or 0)}


def reverse_points(cur, changes) -> None:
    if changes:
        cur.execute("UPDATE customer_info SET rewards = COALESCE(rewards,0) - %s WHERE customer_id=%s",
                    (changes["points"], changes["customer_id"]))


install_undo(APP, {"add_points": reverse_points})

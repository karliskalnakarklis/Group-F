"""stores (variant A): stores, registers, register sessions and the Z-report.
Owns stores, store_registers and registers_table in stores-db."""
from fastapi import HTTPException
from pydantic import BaseModel, Field

from common.calllog import call_ok, create_app, log, now
from common.db import fail, init_database, insert_rows, money, one, require, transaction

APP = create_app("stores")

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
  SID int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  company_name varchar(50) NOT NULL, employee_id int NOT NULL
);
CREATE TABLE IF NOT EXISTS store_registers (
  register_num int NOT NULL PRIMARY KEY, SID int NOT NULL
);
CREATE TABLE IF NOT EXISTS registers_table (
  register_id int NOT NULL AUTO_INCREMENT PRIMARY KEY,
  open_total float NOT NULL, close_total float DEFAULT NULL, register_num int NOT NULL,
  open_emp_id int NOT NULL, close_emp_id int DEFAULT NULL,
  open_time datetime NOT NULL, close_time datetime DEFAULT NULL,
  drop_time datetime DEFAULT NULL, drop_emp_id int DEFAULT NULL, drop_total float DEFAULT NULL,
  note varchar(100) DEFAULT NULL,
  KEY register_num (register_num)
);
"""


def fill(cur, seed: dict) -> None:
    insert_rows(cur, "stores", seed["stores"])
    insert_rows(cur, "store_registers", seed["store_registers"])


@APP.on_event("startup")
def startup():
    init_database(SCHEMA, fill, "stores")


def check_employee(employee_id: int) -> None:
    call_ok("people", "GET", f"/internal/employees/{employee_id}")


def lock_register(cur, register: int) -> None:
    """Register exists (404), and its row is locked so that open and close of
    one register run one after the other."""
    require(cur, "register", "SELECT * FROM store_registers WHERE register_num=%s FOR UPDATE", register)


def open_session_of(cur, register: int, lock: bool = False):
    return one(cur, "SELECT * FROM registers_table WHERE register_num=%s AND close_time IS NULL"
               + (" FOR UPDATE" if lock else ""), register)


# --- contract endpoints ------------------------------------------------------------

class OpenIn(BaseModel):
    employee_id: int
    opening_cash: float = Field(ge=0)


class CloseIn(BaseModel):
    employee_id: int
    counted_cash: float = Field(ge=0)


@APP.post("/registers/{register}/open", status_code=201)
def open_register(register: int, inp: OpenIn):
    check_employee(inp.employee_id)
    with transaction() as cur:
        lock_register(cur, register)
        if open_session_of(cur, register, lock=True):
            raise fail(409, f"register {register} is already open")
        opened = now()
        cur.execute("INSERT INTO registers_table (open_total, register_num, open_emp_id, open_time)"
                    " VALUES (%s,%s,%s,%s)", (float(money(inp.opening_cash)), register, inp.employee_id,
                                              opened.replace(tzinfo=None)))
        return {"session_id": cur.lastrowid, "register": register, "opened_at": opened.isoformat(timespec="seconds")}


@APP.post("/registers/{register}/close")
def close_register(register: int, inp: CloseIn):
    check_employee(inp.employee_id)
    counted = money(inp.counted_cash)
    # Close first, so that no sale or return of this session starts after this point.
    with transaction() as cur:
        lock_register(cur, register)
        session = open_session_of(cur, register, lock=True)
        if not session:
            raise fail(409, f"register {register} is not open")
        sid = session["register_id"]
        cur.execute("UPDATE registers_table SET close_total=%s, close_emp_id=%s, close_time=%s WHERE register_id=%s",
                    (float(counted), inp.employee_id, now().replace(tzinfo=None), sid))
    try:
        totals = call_ok("sales", "GET", f"/internal/sessions/{sid}/totals")
    except HTTPException:
        reopen(register, sid)
        raise
    opening = money(session["open_total"])
    cash_sales, refunds = money(totals["cash_sales"]), money(totals["refunds_total"])
    expected = opening + cash_sales - refunds
    return {"session_id": sid, "register": register, "sales_count": totals["sales_count"],
            "gross_total": float(money(totals["gross_total"])), "tax_total": float(money(totals["tax_total"])),
            "refunds_total": float(refunds), "cash_sales": float(cash_sales),
            "opening_cash": float(opening), "cash_expected": float(expected),
            "counted_cash": float(counted), "difference": float(counted - expected)}


def reopen(register: int, sid: int) -> None:
    """Undo the close after sales could not give the totals."""
    try:
        with transaction() as cur:
            lock_register(cur, register)
            if open_session_of(cur, register):
                log.error("cannot reopen session %s: register %s has another open session", sid, register)
                return
            cur.execute("UPDATE registers_table SET close_total=NULL, close_emp_id=NULL, close_time=NULL"
                        " WHERE register_id=%s", (sid,))
    except Exception:  # noqa: BLE001
        log.exception("reopening session %s failed", sid)


# --- internal calls ------------------------------------------------------------------

@APP.get("/internal/registers/{register}/open-session")
def get_open_session(register: int):
    with transaction() as cur:
        require(cur, "register", "SELECT * FROM store_registers WHERE register_num=%s", register)
        session = open_session_of(cur, register)
        if not session:
            raise fail(409, f"register {register} is not open")
        return {"session_id": session["register_id"], "register": register}


@APP.get("/internal/sessions/{session_id}")
def get_session(session_id: int):
    with transaction() as cur:
        session = require(cur, "session", "SELECT * FROM registers_table WHERE register_id=%s", session_id)
        return {"session_id": session_id, "register": session["register_num"]}


@APP.get("/internal/stores/{sid}/sessions")
def sessions_of_store(sid: int):
    with transaction() as cur:
        require(cur, "store", "SELECT SID FROM stores WHERE SID=%s", sid)
        cur.execute("SELECT s.register_id FROM registers_table s JOIN store_registers r"
                    " ON r.register_num = s.register_num WHERE r.SID=%s ORDER BY s.register_id", (sid,))
        return {"store": sid, "session_ids": [r["register_id"] for r in cur.fetchall()]}

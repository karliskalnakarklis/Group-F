"""Database helpers, seed loading, and receipts and undo (docs/design.md
"Receipts and undo"): the table applied_steps and POST /internal/undo."""
import json
import os
import time
from contextlib import contextmanager
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Callable

import pymysql
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from common.calllog import log, now, request_id

DB = dict(host=os.getenv("DB_HOST", "db"), user=os.getenv("DB_USER", "pos"),
          password=os.getenv("DB_PASSWORD", "pos"), database=os.getenv("DB_NAME", "pos"),
          cursorclass=pymysql.cursors.DictCursor, autocommit=False)
if os.getenv("DB_ISOLATION"):  # for example "READ COMMITTED"
    DB["init_command"] = f"SET SESSION TRANSACTION ISOLATION LEVEL {os.environ['DB_ISOLATION']}"
SEED_PATH = Path(os.getenv("SEED_PATH", "/shared/seed.json"))


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


def load_seed() -> dict:
    return json.loads(SEED_PATH.read_text())


def init_database(schema: str, fill: Callable[[object, dict], None], marker_table: str) -> None:
    """Wait for the database, create the schema, and fill it from the seed if
    it is empty (make up-... starts with empty databases)."""
    for _ in range(90):
        try:
            pymysql.connect(**DB).close()
            break
        except pymysql.err.OperationalError:
            time.sleep(1)
    with transaction() as cur:
        for statement in schema.split(";"):
            if statement.strip():
                cur.execute(statement)
        if one(cur, f"SELECT COUNT(*) AS n FROM `{marker_table}`")["n"]:
            return
        fill(cur, load_seed())


def insert_rows(cur, table: str, rows: list[dict]) -> None:
    for row in rows:
        columns = ", ".join(f"`{c}`" for c in row)
        cur.execute(f"INSERT INTO `{table}` ({columns}) VALUES ({', '.join(['%s'] * len(row))})",
                    list(row.values()))


# --- receipts and undo --------------------------------------------------------------

APPLIED_STEPS = """
CREATE TABLE IF NOT EXISTS applied_steps (
  request_id varchar(100) NOT NULL, step varchar(50) NOT NULL,
  status varchar(10) NOT NULL, changes text NOT NULL, created_at datetime NOT NULL,
  PRIMARY KEY (request_id, step)
)"""


def start_step(cur, step: str):
    """Call at the start of the transaction of a step. Returns None for a new
    step (the receipt is written now, with the row locked until commit); the
    earlier changes for a step that is already done (answer as before, change
    nothing); 409 if the request was already cancelled."""
    try:
        cur.execute("INSERT INTO applied_steps (request_id, step, status, changes, created_at)"
                    " VALUES (%s,%s,'done','[]',%s)", (request_id(), step, now().replace(tzinfo=None)))
        return None
    except pymysql.err.IntegrityError:
        row = one(cur, "SELECT * FROM applied_steps WHERE request_id=%s AND step=%s FOR UPDATE",
                  request_id(), step)
        if row["status"] == "done":
            return json.loads(row["changes"])
        raise fail(409, f"step {step} of this request was cancelled") from None


def finish_step(cur, step: str, changes) -> None:
    """Record what the step changed, in the same transaction as the change."""
    cur.execute("UPDATE applied_steps SET changes=%s WHERE request_id=%s AND step=%s",
                (json.dumps(changes), request_id(), step))


class UndoIn(BaseModel):
    step: str


def install_undo(app: FastAPI, reverse: dict[str, Callable[[object, object], None]]) -> None:
    """POST /internal/undo {step}: undo that step of the request in X-Request-Id.
    'reverse' maps a step name to a function that reverses its changes."""

    @app.post("/internal/undo")
    def undo_step(inp: UndoIn):
        if inp.step not in reverse:
            raise fail(422, f"unknown step {inp.step}")
        for attempt in range(3):
            try:
                with transaction() as cur:
                    try:
                        cur.execute("INSERT INTO applied_steps (request_id, step, status, changes, created_at)"
                                    " VALUES (%s,%s,'undone','[]',%s)",
                                    (request_id(), inp.step, now().replace(tzinfo=None)))
                        return {"step": inp.step, "status": "undone"}  # never arrived: refuse it later
                    except pymysql.err.IntegrityError:
                        pass
                    row = one(cur, "SELECT * FROM applied_steps WHERE request_id=%s AND step=%s FOR UPDATE",
                              request_id(), inp.step)
                    if row["status"] == "done":
                        reverse[inp.step](cur, json.loads(row["changes"]))
                        cur.execute("UPDATE applied_steps SET status='undone' WHERE request_id=%s AND step=%s",
                                    (request_id(), inp.step))
                    return {"step": inp.step, "status": "undone"}
            except pymysql.err.OperationalError as error:  # deadlock with the step itself: try again
                log.warning("undo of %s, attempt %s: %s", inp.step, attempt + 1, error)
        raise fail(500, f"undo of {inp.step} failed")

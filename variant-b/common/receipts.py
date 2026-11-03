"""Receipts and undo (docs/design.md, common decisions): a change made on request
of another service is written together with a row in applied_steps, keyed by
(X-Request-Id, step). POST /internal/undo reverses exactly the recorded changes."""
import json

import pymysql
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import calllog
from .db import one, transaction
from .money import now

SCHEMA = """
CREATE TABLE IF NOT EXISTS applied_steps (
  request_id VARCHAR(64) NOT NULL,
  step VARCHAR(40) NOT NULL,
  status ENUM('done', 'undone') NOT NULL,
  changes JSON NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (request_id, step)
)
"""

UNDO = {}  # step name -> function(cur, changes) that reverses the changes


def undo_handler(step: str):
    def register(fn):
        UNDO[step] = fn
        return fn
    return register


def _receipt(cur, request_id: str, step: str):
    return one(cur, "SELECT status, changes FROM applied_steps WHERE request_id=%s AND step=%s FOR UPDATE",
               request_id, step)


def run_step(step: str, apply, answer):
    """Does a step once per request. apply(cur) makes the change and returns what was
    changed (JSON-able); answer(cur, changes) builds the answer, also for a repeat."""
    request_id = calllog.REQUEST_ID.get()
    for attempt in range(2):
        try:
            with transaction() as cur:
                row = _receipt(cur, request_id, step)
                if row:
                    if row["status"] == "undone":
                        raise HTTPException(status_code=409, detail=f"step {step} of this request was already undone")
                    return answer(cur, json.loads(row["changes"]))
                changes = apply(cur)
                cur.execute("INSERT INTO applied_steps (request_id, step, status, changes, created_at)"
                            " VALUES (%s,%s,'done',%s,%s)", (request_id, step, json.dumps(changes),
                                                             now().replace(tzinfo=None)))
                return answer(cur, changes)
        except pymysql.err.IntegrityError:
            if attempt:  # the same step of the same request arrived twice at once
                raise
    raise AssertionError("unreachable")


class UndoIn(BaseModel):
    step: str


router = APIRouter()


@router.post("/internal/undo")
def undo(inp: UndoIn):
    request_id = calllog.REQUEST_ID.get()
    for attempt in range(2):
        try:
            with transaction() as cur:
                row = _receipt(cur, request_id, inp.step)
                if row is None:  # not arrived yet, or never will: refuse a late arrival
                    cur.execute("INSERT INTO applied_steps (request_id, step, status, changes, created_at)"
                                " VALUES (%s,%s,'undone',NULL,%s)", (request_id, inp.step, now().replace(tzinfo=None)))
                elif row["status"] == "done":
                    UNDO[inp.step](cur, json.loads(row["changes"]))
                    cur.execute("UPDATE applied_steps SET status='undone' WHERE request_id=%s AND step=%s",
                                (request_id, inp.step))
            return {"request_id": request_id, "step": inp.step, "status": "undone"}
        except pymysql.err.IntegrityError:
            if attempt:
                raise
    raise AssertionError("unreachable")

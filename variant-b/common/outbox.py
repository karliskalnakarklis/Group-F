"""Transactional outbox over HTTP (docs/design.md, "Ledger delivery to reporting").
A row is written in the same transaction as the business change, delivered
right after the commit, and retried by a background task until it is delivered,
always with the X-Request-Id of the original request."""
import json
import sys
import threading
import time
from datetime import timedelta

from fastapi import HTTPException

from . import calllog
from .client import call
from .db import one, transaction
from .money import now

SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_outbox (
  entry_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  kind VARCHAR(20) NOT NULL,
  payload JSON NOT NULL,
  request_id VARCHAR(64) NOT NULL,
  created_at DATETIME(3) NOT NULL,
  delivered_at DATETIME(3) NULL,
  KEY undelivered (delivered_at, entry_id)
)
"""


def add(cur, kind: str, payload: dict) -> int:
    cur.execute("INSERT INTO ledger_outbox (kind, payload, request_id, created_at) VALUES (%s,%s,%s,%s)",
                (kind, json.dumps(payload), calllog.REQUEST_ID.get(), now().replace(tzinfo=None)))
    return cur.lastrowid


def deliver(target: str, paths: dict, entry_id: int) -> bool:
    """Sends one row; marks it delivered on 200. Never raises."""
    try:
        with transaction() as cur:
            row = one(cur, "SELECT * FROM ledger_outbox WHERE entry_id=%s", entry_id)
        if row is None or row["delivered_at"] is not None:
            return True
        response = call(target, "POST", paths[row["kind"]], json.loads(row["payload"]), request_id=row["request_id"])
        if response.status_code != 200:
            return False
        with transaction() as cur:
            cur.execute("UPDATE ledger_outbox SET delivered_at=%s WHERE entry_id=%s AND delivered_at IS NULL",
                        (now().replace(tzinfo=None), entry_id))
        return True
    except HTTPException:
        return False
    except Exception as error:  # noqa: BLE001
        print(f"outbox: delivery of entry {entry_id} failed: {error!r}", file=sys.stderr, flush=True)
        return False


def start_retry(target: str, paths: dict, interval: float = 2.0, min_age: float = 2.0) -> None:
    """Every interval seconds: undelivered rows older than min_age, oldest first,
    until the first failure."""

    def loop():
        while True:
            time.sleep(interval)
            try:
                with transaction() as cur:
                    cur.execute("SELECT entry_id FROM ledger_outbox WHERE delivered_at IS NULL"
                                " AND created_at < %s ORDER BY entry_id LIMIT 100",
                                ((now() - timedelta(seconds=min_age)).replace(tzinfo=None),))
                    ids = [r["entry_id"] for r in cur.fetchall()]
                for entry_id in ids:
                    if not deliver(target, paths, entry_id):
                        break
            except Exception:  # noqa: BLE001  (database down: try again next round)
                pass

    threading.Thread(target=loop, name="outbox-retry", daemon=True).start()

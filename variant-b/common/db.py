"""The service's own MariaDB: one transaction per block, READ COMMITTED, and
503 "<service> database unavailable" when the database cannot be reached."""
import os
import time
from contextlib import contextmanager
from pathlib import Path

import pymysql
from fastapi import HTTPException

from . import calllog

DB = dict(host=os.getenv("DB_HOST", "localhost"), user=os.getenv("DB_USER", "pos"),
          password=os.getenv("DB_PASSWORD", "pos"), database=os.getenv("DB_NAME", "pos"),
          cursorclass=pymysql.cursors.DictCursor, autocommit=False, connect_timeout=2,
          init_command="SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")


def unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail=f"{calllog.SERVICE['name']} database unavailable")


@contextmanager
def transaction():
    try:
        conn = pymysql.connect(**DB)
    except pymysql.err.Error:
        raise unavailable() from None
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except (pymysql.err.OperationalError, pymysql.err.InterfaceError) as error:
        try:
            conn.rollback()
        except pymysql.err.Error:
            pass
        if isinstance(error, pymysql.err.OperationalError) and error.args and error.args[0] in (1205, 1213):
            raise  # lock wait timeout or deadlock: a real error of this request
        raise unavailable() from error
    except BaseException:
        conn.rollback()
        raise
    finally:
        try:
            conn.close()
        except pymysql.err.Error:
            pass


def one(cur, sql: str, *args):
    cur.execute(sql, args)
    return cur.fetchone()


def require(cur, what: str, sql: str, *args):
    row = one(cur, sql, *args)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{what} not found")
    return row


def wait_for_db(seconds: int = 90) -> None:
    for _ in range(seconds):
        try:
            pymysql.connect(**DB).close()
            return
        except pymysql.err.Error:
            time.sleep(1)


def create_schema(*sql_texts: str) -> None:
    with transaction() as cur:
        for text in sql_texts:
            for statement in text.split(";"):
                if statement.strip():
                    cur.execute(statement)


def schema_file(module_file: str) -> str:
    return (Path(module_file).parent / "schema.sql").read_text()

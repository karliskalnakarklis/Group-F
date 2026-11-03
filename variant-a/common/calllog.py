"""Call log, request id and calls between services (docs/contract.md "Call log",
docs/design.md "Conventions for calls between services").

Every service builds its app with create_app(). The middleware logs every
incoming request; call() logs every outgoing call and passes X-Request-Id and
X-Step-Key on."""
import contextvars
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

SERVICE = os.environ.get("SERVICE_NAME", "unknown")
ZURICH = ZoneInfo("Europe/Zurich")
LOG_DIR = Path(os.getenv("CALL_LOG_DIR", "/logs"))
CALL_TIMEOUT = float(os.getenv("CALL_TIMEOUT", "2"))
REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
STEP_KEY: contextvars.ContextVar[str] = contextvars.ContextVar("step_key", default="")

log = logging.getLogger(SERVICE)
_write_lock = threading.Lock()
_client = httpx.Client(timeout=CALL_TIMEOUT)


def now() -> datetime:
    return datetime.now(ZURICH)


def request_id() -> str:
    rid = REQUEST_ID.get()
    if not rid:  # background work outside a request
        rid = uuid.uuid4().hex
        REQUEST_ID.set(rid)
    return rid


def step_key() -> str:
    """Key of the receipts (applied_steps) of this request. Unlike X-Request-Id,
    the client cannot choose it: the first service without X-Step-Key creates it."""
    key = STEP_KEY.get()
    if not key:  # background work outside a request
        key = uuid.uuid4().hex
        STEP_KEY.set(key)
    return key


def write_log(direction: str, method: str, target: str, path: str, status: int | None, started: float,
              rid: str | None = None) -> None:
    entry = {
        "time": now().isoformat(timespec="milliseconds"), "service": SERVICE, "request_id": rid or request_id(),
        "direction": direction, "method": method, "target": target, "path": path,
        "status": status, "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    with _write_lock, (LOG_DIR / f"{SERVICE}.jsonl").open("a") as file:
        file.write(json.dumps(entry) + "\n")


def create_app(title: str) -> FastAPI:
    app = FastAPI(title=title)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    @app.middleware("http")
    async def call_log(request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        token = REQUEST_ID.set(rid)
        key_token = STEP_KEY.set(request.headers.get("X-Step-Key") or uuid.uuid4().hex)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001  unexpected error: answer 500 as JSON, still log it
            log.exception("unhandled error")
            response = JSONResponse({"detail": "internal error"}, status_code=500)
        finally:
            STEP_KEY.reset(key_token)
            REQUEST_ID.reset(token)
        write_log("in", request.method, SERVICE, request.url.path, response.status_code, started, rid)
        response.headers["X-Request-Id"] = rid
        return response

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


# --- calls to other services ---------------------------------------------------------

def call(target: str, method: str, path: str, *, json_body=None, params=None,
         timeout: float | None = None) -> httpx.Response:
    """One call to another service. No answer within the timeout, or no
    connection: 503 '<target> unavailable'."""
    started = time.perf_counter()
    status = None
    try:
        response = _client.request(method, f"http://{target}:8000{path}", json=json_body, params=params,
                                   headers={"X-Request-Id": request_id(), "X-Step-Key": step_key()},
                                   timeout=timeout or CALL_TIMEOUT)
        status = response.status_code
        return response
    except httpx.HTTPError:
        status = 503
        raise HTTPException(503, f"{target} unavailable") from None
    finally:
        write_log("out", method, target, path, status, started)


def detail_of(response: httpx.Response) -> str:
    try:
        return response.json()["detail"]
    except Exception:  # noqa: BLE001
        return response.text or f"error {response.status_code}"


def call_ok(target: str, method: str, path: str, **kw):
    """call(), and pass an error answer on unchanged (status and detail)."""
    response = call(target, method, path, **kw)
    if response.status_code >= 400:
        raise HTTPException(response.status_code, detail_of(response))
    return response.json()


def undo(target: str, step: str) -> None:
    """Send the undo of one step of this request. A failed undo is logged."""
    try:
        response = call(target, "POST", "/internal/undo", json_body={"step": step})
        if response.status_code != 200:
            log.error("undo of %s at %s failed: %s %s", step, target, response.status_code, response.text)
    except HTTPException as error:
        log.error("undo of %s at %s failed: %s", step, target, error.detail)


class Steps:
    """The writes a leader made in other services, undone in reverse order if
    the request fails. A step is recorded before it is sent, so that a step
    that failed or timed out is undone as well."""

    def __init__(self):
        self.done: list[tuple[str, str]] = []

    def run(self, target: str, step: str, path: str, body: dict):
        self.done.append((target, step))
        return call_ok(target, "POST", path, json_body=body)

    def undo_all(self) -> None:
        for target, step in reversed(self.done):
            undo(target, step)
        self.done.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.undo_all()
        return False

"""Call log (docs/contract.md, "Call log"): one JSON line per request received
and per call sent, in /logs/<service>.jsonl. The X-Request-Id of the request
being served is kept in REQUEST_ID, so that outgoing calls pass it on."""
import json
import os
import threading
import time
import uuid
from contextvars import ContextVar
from pathlib import Path

from .money import now

REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
LOG_DIR = Path(os.getenv("CALL_LOG_DIR", "/logs"))
SERVICE = {"name": "unknown"}
_lock = threading.Lock()


def init(service: str) -> None:
    SERVICE["name"] = service
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def write(direction: str, method: str, target: str, path: str, status: int, duration_ms: float,
          request_id: str | None) -> None:
    entry = {"time": now().isoformat(timespec="milliseconds"), "service": SERVICE["name"],
             "request_id": request_id, "direction": direction, "method": method, "target": target,
             "path": path, "status": status, "duration_ms": round(duration_ms, 2)}
    with _lock, (LOG_DIR / f"{SERVICE['name']}.jsonl").open("a") as log:
        log.write(json.dumps(entry) + "\n")


def new_request_id() -> str:
    return uuid.uuid4().hex


class CallLog:
    """ASGI middleware: takes X-Request-Id from the request (or creates one), keeps it
    in REQUEST_ID for the handler, and logs the request with its status."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        request_id = headers.get(b"x-request-id", b"").decode() or new_request_id()
        if b"x-request-id" not in headers:
            scope = {**scope, "headers": [*scope.get("headers", []), (b"x-request-id", request_id.encode())]}
        token = REQUEST_ID.set(request_id)
        status = {"code": 500}
        started = time.perf_counter()

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message = {**message, "headers": [*message.get("headers", []),
                                                  (b"x-request-id", request_id.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            write("in", scope["method"], SERVICE["name"], scope["path"], status["code"],
                  (time.perf_counter() - started) * 1000, request_id)
            REQUEST_ID.reset(token)

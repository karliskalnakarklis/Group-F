"""Calls between services ("Conventions for calls between services"): every call
carries the X-Request-Id, is logged, and fails with 503 "<service> unavailable"
when the service does not answer within the timeout or cannot be reached."""
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import httpx
from fastapi import HTTPException

from . import calllog

TIMEOUT = 2.0
_client = httpx.Client(timeout=TIMEOUT)
# The name of a stopped container takes seconds to fail in Docker's DNS, and the
# httpx timeout does not cover the lookup; so the lookup gets its own deadline.
_dns = ThreadPoolExecutor(max_workers=16, thread_name_prefix="dns")


def _address(host: str, timeout: float) -> str | None:
    try:
        return _dns.submit(socket.gethostbyname, host).result(timeout=timeout)
    except (FutureTimeout, OSError):
        return None


def call(target: str, method: str, path: str, json=None, *, content: bytes | None = None,
         headers: dict | None = None, timeout: float = TIMEOUT, request_id: str | None = None) -> httpx.Response:
    request_id = request_id or calllog.REQUEST_ID.get() or calllog.new_request_id()
    started = time.perf_counter()
    try:
        address = _address(target, min(timeout, TIMEOUT))
        if address is None:
            raise httpx.ConnectError(f"cannot resolve {target}")
        left = max(0.1, timeout - (time.perf_counter() - started))
        response = _client.request(method, f"http://{address}:8000{path}", json=json, content=content,
                                   headers={**(headers or {}), "Host": target, "X-Request-Id": request_id},
                                   timeout=left)
    except httpx.HTTPError:
        calllog.write("out", method, target, path.split("?")[0], 503, (time.perf_counter() - started) * 1000,
                      request_id)
        raise HTTPException(status_code=503, detail=f"{target} unavailable") from None
    calllog.write("out", method, target, path.split("?")[0], response.status_code,
                  (time.perf_counter() - started) * 1000, request_id)
    return response


def expect(response: httpx.Response, status: int = 200) -> dict:
    """The answer of a call, or its error passed on unchanged (status and detail)."""
    if response.status_code == status:
        return response.json()
    try:
        detail = response.json()["detail"]
    except Exception:  # noqa: BLE001
        detail = response.text or "unexpected answer"
    raise HTTPException(status_code=response.status_code, detail=detail)


def undo(target: str, step: str) -> None:
    """Sends the undo of a step of the current request. A failed undo is logged as an error."""
    try:
        response = call(target, "POST", "/internal/undo", {"step": step})
        if response.status_code == 200:
            return
        problem = f"status {response.status_code}: {response.text}"
    except HTTPException as error:
        problem = error.detail
    print(f"ERROR undo of {step} at {target} failed for request {calllog.REQUEST_ID.get()}: {problem}",
          file=sys.stderr, flush=True)

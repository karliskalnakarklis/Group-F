"""Gateway of variant A: routing only. Every contract endpoint goes, unchanged,
to the leader of its use case (docs/design.md, use case table of variant A)."""
import time

import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from common.calllog import create_app, request_id, write_log

APP = create_app("Frischwerk PoS gateway (variant A)")
LEADER_TIMEOUT = 20.0
_client = httpx.AsyncClient(timeout=LEADER_TIMEOUT)

# first path segment -> leader
LEADERS = {
    "products": "inventory",
    "purchase-orders": "inventory",
    "customers": "people",
    "registers": "stores",
    "gift-cards": "sales",
    "sales": "sales",
    "returns": "sales",
    "reports": "sales",
}


@APP.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def route(path: str, request: Request):
    leader = LEADERS.get(path.split("/", 1)[0])
    if leader is None:
        return JSONResponse({"detail": "not found"}, status_code=404)
    body = await request.body()
    started = time.perf_counter()
    status = None
    try:
        answer = await _client.request(
            request.method, f"http://{leader}:8000/{path}", params=request.query_params, content=body,
            headers={"X-Request-Id": request_id(),
                     "Content-Type": request.headers.get("content-type", "application/json")})
        status = answer.status_code
    except httpx.HTTPError:
        status = 503
        return JSONResponse({"detail": f"{leader} unavailable"}, status_code=503)
    finally:
        write_log("out", request.method, leader, f"/{path}", status, started)
    return Response(answer.content, status_code=answer.status_code,
                    media_type=answer.headers.get("content-type", "application/json"))

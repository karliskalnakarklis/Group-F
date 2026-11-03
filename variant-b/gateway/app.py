"""gateway (variant B): routing only. Every contract request goes unchanged, on the
same method and path, to the leader of its use case; its answer comes back
unchanged. Waits up to 20 s for the leader."""
from fastapi import FastAPI, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from common import calllog
from common.client import call

SERVICE = "gateway"
LEADER_TIMEOUT = 20.0
LEADERS = {  # first path segment -> leader of the use case (docs/design.md, variant B)
    "products": "purchasing",
    "purchase-orders": "purchasing",
    "customers": "customers",
    "gift-cards": "till",
    "registers": "till",
    "sales": "till",
    "returns": "till",
    "reports": "reporting",
}

calllog.init(SERVICE)
APP = FastAPI(title="gateway")
APP.add_middleware(calllog.CallLog)


@APP.get("/health")
def health():
    return {"status": "ok"}


@APP.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def route(path: str, request: Request):
    leader = LEADERS.get(path.split("/")[0])
    if leader is None:
        raise HTTPException(status_code=404, detail="not found")
    body = await request.body()
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    headers = {"Content-Type": request.headers["content-type"]} if "content-type" in request.headers else {}
    response = await run_in_threadpool(call, leader, request.method, target, content=body or None, headers=headers,
                                       timeout=LEADER_TIMEOUT, request_id=calllog.REQUEST_ID.get())
    return Response(content=response.content, status_code=response.status_code,
                    media_type=response.headers.get("content-type"))

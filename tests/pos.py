"""Small client used by the tests and the measurement scripts. It only speaks
the contract in docs/contract.md (version 1) and, with POS_LEVEL=v2, the
change requests in docs/change-requests.md."""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

URL = os.environ.get("POS_URL", "http://localhost:8000").rstrip("/")
LEVEL = os.environ.get("POS_LEVEL") or "v1"
SEED = json.loads((Path(__file__).resolve().parent.parent / "shared" / "seed.json").read_text())
PRODUCTS = {p["product_id"]: p for p in SEED["product_inventory"]}
TAX_RATE = Decimal(str(max(SEED["tax_table"], key=lambda r: r["tax_year"])["tax_rate"]))
REDUCED = {"Dairy", "Produce", "Beef", "Poultry", "Pasta", "DryGoods", "PetFood"}
ZURICH = ZoneInfo("Europe/Zurich")

CASHIER = 2  # an employee from the seed
http = httpx.Client(timeout=10.0)


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def today() -> str:
    return datetime.now(ZURICH).date().isoformat()


def request(method: str, path: str, body: dict | None = None, request_id: str | None = None) -> httpx.Response:
    headers = {"X-Request-Id": request_id or uuid.uuid4().hex}
    return http.request(method, f"{URL}{path}", json=body, headers=headers)


def get(path: str, **kw) -> httpx.Response:
    return request("GET", path, **kw)


def post(path: str, body: dict | None = None, **kw) -> httpx.Response:
    return request("POST", path, body or {}, **kw)


def ok(response: httpx.Response, status: int = 200) -> dict:
    assert response.status_code == status, f"expected {status}, got {response.status_code}: {response.text}"
    return response.json()


def assert_error(response: httpx.Response, status: int, keyword: str | None) -> None:
    assert response.status_code == status, f"expected {status}, got {response.status_code}: {response.text}"
    try:
        detail = response.json()["detail"]
    except Exception:  # noqa: BLE001
        raise AssertionError(f"error is not JSON with a 'detail' field: {response.text}") from None
    if keyword is not None:
        assert isinstance(detail, str) and keyword in detail.lower(), (
            f"detail must contain {keyword!r}, got: {detail!r}"
        )


def close_enough(actual, expected, what: str = "amount") -> None:
    assert abs(Decimal(str(actual)) - Decimal(str(expected))) <= Decimal("0.01"), (
        f"{what}: expected {expected}, got {actual}"
    )


# --- domain helpers --------------------------------------------------------------

def stock(product_id: int) -> int:
    return ok(get(f"/products/{product_id}"))["in_stock"]


def price(product_id: int) -> Decimal:
    return money(PRODUCTS[product_id]["unit_price"])


def vat_rate(product_id: int) -> Decimal:
    return Decimal("0.026") if PRODUCTS[product_id]["productType"] in REDUCED else Decimal("0.081")


def expected_sale(lines: list[dict]) -> dict:
    """subtotal, tax, total (and vat per rate in v2) for lines [{product_id, qty}]."""
    if LEVEL == "v1":
        subtotal = money(sum(line["qty"] * price(line["product_id"]) for line in lines))
        tax = money(subtotal * TAX_RATE)
        return {"subtotal": subtotal, "tax": tax, "total": subtotal + tax}
    gross: dict[Decimal, Decimal] = {}
    for line in lines:
        rate = vat_rate(line["product_id"])
        gross[rate] = gross.get(rate, Decimal(0)) + line["qty"] * price(line["product_id"])
    vat = [{"rate": rate, "gross": money(g), "vat": money(g * rate / (1 + rate))} for rate, g in sorted(gross.items())]
    for entry in vat:
        entry["net"] = entry["gross"] - entry["vat"]
    total = sum((e["gross"] for e in vat), Decimal(0))
    tax = sum((e["vat"] for e in vat), Decimal(0))
    return {"subtotal": total - tax, "tax": tax, "total": total, "vat": vat}


def expected_refund(sale: dict, lines: list[dict]) -> Decimal:
    prices = {line["product_id"]: money(line["unit_price"]) for line in sale["lines"]}
    amount = money(sum(line["qty"] * prices[line["product_id"]] for line in lines))
    if LEVEL == "v1":
        return amount + money(amount * TAX_RATE)
    return amount


def open_register(register: int, opening_cash: float = 200.0) -> dict:
    """Open the register; if it is open already, close it first, so that a fresh session starts."""
    response = post(f"/registers/{register}/open", {"employee_id": CASHIER, "opening_cash": opening_cash})
    if response.status_code == 409:
        ok(post(f"/registers/{register}/close", {"employee_id": CASHIER, "counted_cash": 0}))
        response = post(f"/registers/{register}/open", {"employee_id": CASHIER, "opening_cash": opening_cash})
    return ok(response, 201)


def ensure_open(register: int) -> None:
    response = post(f"/registers/{register}/open", {"employee_id": CASHIER, "opening_cash": 200.0})
    assert response.status_code in (201, 409), response.text


def ensure_closed(register: int) -> None:
    response = post(f"/registers/{register}/close", {"employee_id": CASHIER, "counted_cash": 0})
    assert response.status_code in (200, 409), response.text


def sell(register: int, lines: list[dict], customer_id: int | None = None, method: str = "cash",
         **kw) -> httpx.Response:
    total = expected_sale(lines)["total"]
    body = {"register": register, "employee_id": CASHIER, "lines": lines,
            "payments": [{"method": method, "amount": float(total)}]}
    if customer_id is not None:
        body["customer_id"] = customer_id
    return post("/sales", body, **kw)


def new_customer(name: str = "Test") -> dict:
    return ok(post("/customers", {"first_name": name, "last_name": "Kunde", "email": f"{uuid.uuid4().hex[:8]}@example.com",
                                  "phone": "+41 31 000 00 00", "street": "Testweg 1", "zip_code": 3000,
                                  "city": "Bern"}), 201)


def wait_for(seconds: float = 60.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if http.get(f"{URL}/health").status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False

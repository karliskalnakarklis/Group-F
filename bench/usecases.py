"""The use cases that the measurement scripts run, one request each.
Every function does its setup first and returns the response of the one
measured request."""
import uuid

import pos

REGISTER = 1


def product_lookup(rid):
    return pos.get("/products/5", request_id=rid)


def checkout(rid):
    customer = pos.SEED["customer_info"][0]["customer_id"]
    return pos.sell(REGISTER, [{"product_id": 5, "qty": 1}, {"product_id": 56, "qty": 1}],
                    customer_id=customer, request_id=rid)


def return_item(rid):
    customer = pos.SEED["customer_info"][1]["customer_id"]
    sale = pos.ok(pos.sell(REGISTER, [{"product_id": 20, "qty": 1}], customer_id=customer), 201)
    return pos.post("/returns", {"sale_id": sale["sale_id"], "register": REGISTER, "employee_id": pos.CASHIER,
                                 "lines": [{"product_id": 20, "qty": 1}]}, request_id=rid)


def purchase_order(rid):
    return pos.post("/purchase-orders", {"vendor_id": 1, "employee_id": pos.CASHIER,
                                         "lines": [{"product_id": 1, "qty": 5}]}, request_id=rid)


def goods_receipt(rid):
    order = pos.ok(pos.post("/purchase-orders", {"vendor_id": 1, "employee_id": pos.CASHIER,
                                                 "lines": [{"product_id": 1, "qty": 5}]}), 201)
    return pos.post(f"/purchase-orders/{order['purchase_order_id']}/receipt", {"employee_id": pos.CASHIER},
                    request_id=rid)


def z_report(rid):
    pos.open_register(2)
    pos.ok(pos.sell(2, [{"product_id": 5, "qty": 1}]), 201)
    return pos.post("/registers/2/close", {"employee_id": pos.CASHIER, "counted_cash": 0}, request_id=rid)


def sales_report(rid):
    day = pos.today()
    return pos.get(f"/reports/sales?store=1&from={day}&to={day}", request_id=rid)


USE_CASES = {
    "product_lookup": product_lookup,
    "checkout": checkout,
    "return": return_item,
    "purchase_order": purchase_order,
    "goods_receipt": goods_receipt,
    "z_report": z_report,
    "sales_report": sales_report,
}


def new_id() -> str:
    return uuid.uuid4().hex

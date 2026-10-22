"""Purchase orders and goods receipt."""
import pos

VENDOR = 1
OWN_PRODUCT = next(p for p in pos.SEED["product_inventory"] if p["vendor_id"] == VENDOR)["product_id"]
OTHER_PRODUCT = next(p for p in pos.SEED["product_inventory"] if p["vendor_id"] != VENDOR)["product_id"]


def order(lines, vendor=VENDOR):
    return pos.post("/purchase-orders", {"vendor_id": vendor, "employee_id": pos.CASHIER, "lines": lines})


def test_order_is_open_and_costed():
    created = pos.ok(order([{"product_id": OWN_PRODUCT, "qty": 4}]), 201)
    assert created["status"] == "open"
    pos.close_enough(created["total_cost"], 4 * pos.money(pos.PRODUCTS[OWN_PRODUCT]["cost"]), "total_cost")
    assert pos.ok(pos.get(f"/purchase-orders/{created['purchase_order_id']}"))["status"] == "open"


def test_receipt_adds_stock_once():
    created = pos.ok(order([{"product_id": OWN_PRODUCT, "qty": 7}]), 201)
    before = pos.stock(OWN_PRODUCT)
    path = f"/purchase-orders/{created['purchase_order_id']}/receipt"
    assert pos.ok(pos.post(path, {"employee_id": pos.CASHIER}))["status"] == "received"
    assert pos.stock(OWN_PRODUCT) == before + 7
    pos.assert_error(pos.post(path, {"employee_id": pos.CASHIER}), 409, "received")
    assert pos.stock(OWN_PRODUCT) == before + 7


def test_open_order_does_not_change_stock():
    before = pos.stock(OWN_PRODUCT)
    pos.ok(order([{"product_id": OWN_PRODUCT, "qty": 5}]), 201)
    assert pos.stock(OWN_PRODUCT) == before


def test_product_of_another_vendor():
    pos.assert_error(order([{"product_id": OWN_PRODUCT, "qty": 1}, {"product_id": OTHER_PRODUCT, "qty": 1}]),
                     422, "vendor")


def test_unknown_vendor():
    pos.assert_error(order([{"product_id": OWN_PRODUCT, "qty": 1}], vendor=99999), 404, "not found")

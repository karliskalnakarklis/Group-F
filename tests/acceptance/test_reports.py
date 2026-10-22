"""Sales report per store and period."""
import pos

STORE, REGISTER = 2, 3  # register 3 stands in store 2


def report(store: int = STORE) -> dict:
    day = pos.today()
    return pos.ok(pos.get(f"/reports/sales?store={store}&from={day}&to={day}"))


def test_report_counts_a_new_sale():
    pos.ensure_open(REGISTER)
    before = report()
    sale = pos.ok(pos.sell(REGISTER, [{"product_id": 45, "qty": 2}]), 201)
    after = report()
    assert after["sales_count"] == before["sales_count"] + 1
    pos.close_enough(after["gross_total"], pos.money(before["gross_total"]) + pos.money(sale["total"]), "gross_total")
    pos.close_enough(after["tax_total"], pos.money(before["tax_total"]) + pos.money(sale["tax"]), "tax_total")


def test_report_counts_refunds():
    pos.ensure_open(REGISTER)
    sale = pos.ok(pos.sell(REGISTER, [{"product_id": 45, "qty": 2}]), 201)
    before = report()
    returned = pos.ok(pos.post("/returns", {"sale_id": sale["sale_id"], "register": REGISTER,
                                            "employee_id": pos.CASHIER, "lines": [{"product_id": 45, "qty": 1}]}), 201)
    after = report()
    refund = pos.money(returned["refund_amount"])
    assert after["sales_count"] == before["sales_count"]
    pos.close_enough(after["refunds_total"], pos.money(before["refunds_total"]) + refund, "refunds_total")
    pos.close_enough(after["net_revenue"], pos.money(after["gross_total"]) - pos.money(after["refunds_total"]),
                     "net_revenue")


def test_top_products():
    pos.ensure_open(REGISTER)
    pos.ok(pos.sell(REGISTER, [{"product_id": 61, "qty": 400}]), 201)
    top = report()["top_products"]
    assert 1 <= len(top) <= 5
    quantities = [entry["qty"] for entry in top]
    assert quantities == sorted(quantities, reverse=True)
    assert top[0]["product_id"] == 61


def test_other_store_is_not_affected():
    other_before = report(store=1)
    pos.ensure_open(REGISTER)
    pos.ok(pos.sell(REGISTER, [{"product_id": 45, "qty": 1}]), 201)
    assert report(store=1)["sales_count"] == other_before["sales_count"]


def test_unknown_store():
    day = pos.today()
    pos.assert_error(pos.get(f"/reports/sales?store=99&from={day}&to={day}"), 404, "not found")

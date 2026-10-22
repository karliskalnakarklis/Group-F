"""CR1: Swiss VAT, gross prices, VAT per rate on sales, Z-report and sales report."""
from decimal import Decimal

import pos

FOOD, NON_FOOD = 5, 56  # Produce (2.6%) and Bathroom (8.1%)


def check_vat(actual: list[dict], expected: list[dict]) -> None:
    assert [Decimal(str(e["rate"])) for e in actual] == [e["rate"] for e in expected], f"rates: {actual}"
    for a, e in zip(actual, expected):
        for key in ("net", "vat", "gross"):
            pos.close_enough(a[key], e[key], f"vat {e['rate']} {key}")


def vat_lines(lines):
    expected = pos.expected_sale(lines)
    assert "vat" in expected, "run with POS_LEVEL=v2"
    return expected


def test_food_has_the_reduced_rate_included(till):
    lines = [{"product_id": FOOD, "qty": 2}]
    expected = vat_lines(lines)
    sale = pos.ok(pos.sell(till, lines), 201)
    pos.close_enough(sale["total"], 2 * pos.price(FOOD), "total is the gross price")
    check_vat(sale["vat"], expected["vat"])
    pos.close_enough(sale["tax"], expected["tax"], "tax")
    pos.close_enough(sale["subtotal"], expected["subtotal"], "subtotal")


def test_other_goods_have_the_standard_rate(till):
    lines = [{"product_id": NON_FOOD, "qty": 1}]
    sale = pos.ok(pos.sell(till, lines), 201)
    check_vat(sale["vat"], vat_lines(lines)["vat"])


def test_mixed_sale_lists_both_rates_lowest_first(till):
    lines = [{"product_id": NON_FOOD, "qty": 1}, {"product_id": FOOD, "qty": 3}]
    sale = pos.ok(pos.sell(till, lines), 201)
    check_vat(sale["vat"], vat_lines(lines)["vat"])
    pos.close_enough(sale["total"], sum(e["gross"] for e in vat_lines(lines)["vat"]), "total")


def test_refund_is_the_gross_price(till):
    sale = pos.ok(pos.sell(till, [{"product_id": NON_FOOD, "qty": 2}]), 201)
    returned = pos.ok(pos.post("/returns", {"sale_id": sale["sale_id"], "register": till, "employee_id": pos.CASHIER,
                                            "lines": [{"product_id": NON_FOOD, "qty": 1}]}), 201)
    pos.close_enough(returned["refund_amount"], pos.price(NON_FOOD), "refund_amount")


def test_z_report_shows_vat_per_rate():
    register = 4
    pos.open_register(register)
    a = pos.ok(pos.sell(register, [{"product_id": FOOD, "qty": 1}, {"product_id": NON_FOOD, "qty": 1}]), 201)
    b = pos.ok(pos.sell(register, [{"product_id": FOOD, "qty": 2}]), 201)
    z = pos.ok(pos.post(f"/registers/{register}/close", {"employee_id": pos.CASHIER, "counted_cash": 0}))
    sums: dict[Decimal, dict] = {}
    for sale in (a, b):
        for entry in sale["vat"]:
            s = sums.setdefault(Decimal(str(entry["rate"])), {"net": Decimal(0), "vat": Decimal(0), "gross": Decimal(0)})
            for key in s:
                s[key] += pos.money(entry[key])
    check_vat(z["vat"], [{"rate": r, **v} for r, v in sorted(sums.items())])
    pos.close_enough(z["tax_total"], sum(v["vat"] for v in sums.values()), "tax_total")


def test_sales_report_shows_vat_per_rate():
    register, store = 3, 2
    pos.ensure_open(register)
    day = pos.today()
    path = f"/reports/sales?store={store}&from={day}&to={day}"
    before = {Decimal(str(e["rate"])): e for e in pos.ok(pos.get(path))["vat"]}
    sale = pos.ok(pos.sell(register, [{"product_id": NON_FOOD, "qty": 1}]), 201)
    after = {Decimal(str(e["rate"])): e for e in pos.ok(pos.get(path))["vat"]}
    rate = Decimal("0.081")
    old = pos.money(before[rate]["vat"]) if rate in before else Decimal(0)
    pos.close_enough(after[rate]["vat"], old + pos.money(sale["vat"][0]["vat"]), "report vat 8.1%")

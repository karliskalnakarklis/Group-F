"""Checkout: totals, stock, payments, reward points, and failures that change nothing."""
import pos

FOOD, NON_FOOD = 5, 56  # Produce and Bathroom


def check_totals(sale: dict, lines: list[dict]) -> None:
    expected = pos.expected_sale(lines)
    for key in ("subtotal", "tax", "total"):
        pos.close_enough(sale[key], expected[key], key)
    for line in sale["lines"]:
        pos.close_enough(line["unit_price"], pos.price(line["product_id"]), "unit_price")
        pos.close_enough(line["line_total"], pos.money(line["qty"] * pos.price(line["product_id"])), "line_total")


def test_cash_sale_has_correct_totals(till):
    lines = [{"product_id": FOOD, "qty": 2}, {"product_id": NON_FOOD, "qty": 1}]
    sale = pos.ok(pos.sell(till, lines), 201)
    check_totals(sale, lines)
    assert [(l["product_id"], l["qty"]) for l in sale["lines"]] == [(FOOD, 2), (NON_FOOD, 1)]


def test_sale_reduces_stock(till):
    before = pos.stock(FOOD)
    pos.ok(pos.sell(till, [{"product_id": FOOD, "qty": 3}]), 201)
    assert pos.stock(FOOD) == before - 3


def test_sale_can_be_read_again(till):
    sale = pos.ok(pos.sell(till, [{"product_id": 10, "qty": 1}]), 201)
    again = pos.ok(pos.get(f"/sales/{sale['sale_id']}"))
    assert again["sale_id"] == sale["sale_id"]
    assert again["lines"] == sale["lines"]
    pos.close_enough(again["total"], sale["total"], "total")


def test_customer_earns_reward_points(till):
    customer = pos.new_customer()
    lines = [{"product_id": 40, "qty": 3}]
    sale = pos.ok(pos.sell(till, lines, customer_id=customer["customer_id"]), 201)
    points = int(pos.expected_sale(lines)["total"])
    assert sale["reward_points_earned"] == points
    assert pos.ok(pos.get(f"/customers/{customer['customer_id']}"))["reward_points"] == points


def test_sale_without_customer_earns_nothing(till):
    sale = pos.ok(pos.sell(till, [{"product_id": 40, "qty": 1}]), 201)
    assert sale["reward_points_earned"] == 0


def test_card_and_gift_card_payment(till):
    card = pos.ok(pos.post("/gift-cards", {"amount": 10}), 201)
    lines = [{"product_id": NON_FOOD, "qty": 1}]
    total = pos.expected_sale(lines)["total"]
    body = {"register": till, "employee_id": pos.CASHIER, "lines": lines,
            "payments": [{"method": "gift_card", "gift_card_id": card["gift_card_id"], "amount": 10.0},
                         {"method": "card", "amount": float(total - 10)}]}
    pos.ok(pos.post("/sales", body), 201)
    pos.close_enough(pos.ok(pos.get(f"/gift-cards/{card['gift_card_id']}"))["balance"], 0)


def test_payments_must_add_up_to_the_total(till):
    before = pos.stock(FOOD)
    body = {"register": till, "employee_id": pos.CASHIER, "lines": [{"product_id": FOOD, "qty": 1}],
            "payments": [{"method": "cash", "amount": 1.00}]}
    pos.assert_error(pos.post("/sales", body), 422, "payment")
    assert pos.stock(FOOD) == before


def test_not_enough_stock_changes_nothing(till):
    before = pos.stock(FOOD)
    lines = [{"product_id": FOOD, "qty": 1}, {"product_id": NON_FOOD, "qty": 10_000_000}]
    pos.assert_error(pos.sell(till, lines), 409, "stock")
    assert pos.stock(FOOD) == before, "the first line must not be sold when the second fails"


def test_gift_card_balance_too_low_changes_nothing(till):
    card = pos.ok(pos.post("/gift-cards", {"amount": 5}), 201)
    customer = pos.new_customer()
    before = pos.stock(NON_FOOD)
    lines = [{"product_id": NON_FOOD, "qty": 1}]
    total = pos.expected_sale(lines)["total"]
    body = {"register": till, "employee_id": pos.CASHIER, "customer_id": customer["customer_id"], "lines": lines,
            "payments": [{"method": "gift_card", "gift_card_id": card["gift_card_id"], "amount": float(total)}]}
    pos.assert_error(pos.post("/sales", body), 409, "gift card")
    assert pos.stock(NON_FOOD) == before
    pos.close_enough(pos.ok(pos.get(f"/gift-cards/{card['gift_card_id']}"))["balance"], 5)
    assert pos.ok(pos.get(f"/customers/{customer['customer_id']}"))["reward_points"] == 0


def test_unknown_product_in_sale(till):
    body = {"register": till, "employee_id": pos.CASHIER, "lines": [{"product_id": 99999, "qty": 1}],
            "payments": [{"method": "cash", "amount": 1.0}]}
    pos.assert_error(pos.post("/sales", body), 404, "not found")


def test_unknown_employee_in_sale(till):
    body = {"register": till, "employee_id": 99999, "lines": [{"product_id": FOOD, "qty": 1}],
            "payments": [{"method": "cash", "amount": float(pos.expected_sale([{"product_id": FOOD, "qty": 1}])["total"])}]}
    pos.assert_error(pos.post("/sales", body), 404, "not found")


def test_unknown_customer_in_sale(till):
    pos.assert_error(pos.sell(till, [{"product_id": FOOD, "qty": 1}], customer_id=99999), 404, "not found")


def test_sale_on_closed_register():
    pos.ensure_closed(2)
    pos.assert_error(pos.sell(2, [{"product_id": FOOD, "qty": 1}]), 409, "register")


def test_malformed_sale_is_rejected(till):
    body = {"register": till, "employee_id": pos.CASHIER, "lines": [], "payments": [{"method": "cash", "amount": 1}]}
    assert pos.post("/sales", body).status_code == 422

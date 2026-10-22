"""CR2: loyalty tiers by 12-month spend; returns take points back."""
import math

import pos

BULK = 56  # a product with a high price, bought in quantity to reach the tiers


def buy(till, customer_id: int, qty: int) -> dict:
    return pos.ok(pos.sell(till, [{"product_id": BULK, "qty": qty}], customer_id=customer_id), 201)


def qty_for(amount: float) -> int:
    """Smallest quantity whose sale total is at least amount."""
    qty = 1
    while pos.expected_sale([{"product_id": BULK, "qty": qty}])["total"] < amount:
        qty += 1
    return qty


def customer(customer_id: int) -> dict:
    return pos.ok(pos.get(f"/customers/{customer_id}"))


def test_new_customer_is_bronze():
    c = customer(pos.new_customer()["customer_id"])
    assert c["tier"] == "bronze"
    pos.close_enough(c["spend_12m"], 0, "spend_12m")


def test_bronze_earns_one_point_per_franc(till):
    cid = pos.new_customer()["customer_id"]
    sale = buy(till, cid, 1)
    assert sale["tier"] == "bronze"
    assert sale["reward_points_earned"] == math.floor(sale["total"])


def test_silver_from_500_earns_double(till):
    cid = pos.new_customer()["customer_id"]
    first = buy(till, cid, qty_for(500))
    assert first["tier"] == "bronze", "the tier is determined before the sale"
    assert customer(cid)["tier"] == "silver"
    second = buy(till, cid, 1)
    assert second["tier"] == "silver"
    assert second["reward_points_earned"] == 2 * math.floor(second["total"])


def test_gold_from_2000_earns_triple(till):
    cid = pos.new_customer()["customer_id"]
    buy(till, cid, qty_for(2000))
    assert customer(cid)["tier"] == "gold"
    sale = buy(till, cid, 1)
    assert sale["reward_points_earned"] == 3 * math.floor(sale["total"])


def test_return_takes_points_back_at_the_original_rate(till):
    cid = pos.new_customer()["customer_id"]
    buy(till, cid, qty_for(500))                 # now silver
    sale = buy(till, cid, 2)                     # earned at 2 points per CHF
    before = customer(cid)["reward_points"]
    returned = pos.ok(pos.post("/returns", {"sale_id": sale["sale_id"], "register": till, "employee_id": pos.CASHIER,
                                            "lines": [{"product_id": BULK, "qty": 1}]}), 201)
    assert customer(cid)["reward_points"] == max(0, before - 2 * math.floor(returned["refund_amount"]))


def test_refunds_reduce_spend_and_can_lower_the_tier(till):
    cid = pos.new_customer()["customer_id"]
    qty = qty_for(500)
    sale = buy(till, cid, qty)
    assert customer(cid)["tier"] == "silver"
    returned = pos.ok(pos.post("/returns", {"sale_id": sale["sale_id"], "register": till, "employee_id": pos.CASHIER,
                                            "lines": [{"product_id": BULK, "qty": qty}]}), 201)
    c = customer(cid)
    pos.close_enough(c["spend_12m"], pos.money(sale["total"]) - pos.money(returned["refund_amount"]), "spend_12m")
    assert c["tier"] == "bronze"

"""Returns: refund, restock, never more than sold."""
import pos

PRODUCT = 20


def sale_of(till, qty: int) -> dict:
    return pos.ok(pos.sell(till, [{"product_id": PRODUCT, "qty": qty}]), 201)


def give_back(till, sale_id: int, product_id: int, qty: int):
    return pos.post("/returns", {"sale_id": sale_id, "register": till, "employee_id": pos.CASHIER,
                                 "lines": [{"product_id": product_id, "qty": qty}]})


def test_return_refunds_and_restocks(till):
    sale = sale_of(till, 2)
    before = pos.stock(PRODUCT)
    result = pos.ok(give_back(till, sale["sale_id"], PRODUCT, 1), 201)
    pos.close_enough(result["refund_amount"], pos.expected_refund(sale, [{"product_id": PRODUCT, "qty": 1}]),
                     "refund_amount")
    assert pos.stock(PRODUCT) == before + 1


def test_partial_returns_up_to_the_quantity_sold(till):
    sale = sale_of(till, 3)
    pos.ok(give_back(till, sale["sale_id"], PRODUCT, 1), 201)
    pos.ok(give_back(till, sale["sale_id"], PRODUCT, 2), 201)
    before = pos.stock(PRODUCT)
    pos.assert_error(give_back(till, sale["sale_id"], PRODUCT, 1), 409, "return")
    assert pos.stock(PRODUCT) == before


def test_product_not_in_the_sale(till):
    sale = sale_of(till, 1)
    pos.assert_error(give_back(till, sale["sale_id"], PRODUCT + 1, 1), 409, "return")


def test_unknown_sale(till):
    pos.assert_error(give_back(till, 99999, PRODUCT, 1), 404, "not found")

"""Catalogue, customers and gift cards."""
import pos


def test_gateway_is_up():
    assert pos.get("/health").status_code == 200


def test_product_from_the_seed():
    product = pos.ok(pos.get("/products/5"))
    seed = pos.PRODUCTS[5]
    assert product["name"] == seed["productName"]
    assert product["category"] == seed["productType"]
    pos.close_enough(product["unit_price"], seed["unit_price"], "unit_price")
    pos.close_enough(product["cost"], seed["cost"], "cost")
    assert product["vendor_id"] == seed["vendor_id"]
    assert isinstance(product["in_stock"], int)


def test_unknown_product():
    pos.assert_error(pos.get("/products/99999"), 404, "not found")


def test_create_and_read_customer():
    created = pos.new_customer("Ada")
    customer = pos.ok(pos.get(f"/customers/{created['customer_id']}"))
    assert customer["first_name"] == "Ada"
    assert customer["reward_points"] == 0


def test_customer_from_the_seed():
    seed = pos.SEED["customer_info"][0]
    customer = pos.ok(pos.get(f"/customers/{seed['customer_id']}"))
    assert customer["last_name"] == seed["last_name"]


def test_unknown_customer():
    pos.assert_error(pos.get("/customers/99999"), 404, "not found")


def test_issue_and_read_gift_card():
    card = pos.ok(pos.post("/gift-cards", {"amount": 50}), 201)
    pos.close_enough(card["balance"], 50)
    pos.close_enough(pos.ok(pos.get(f"/gift-cards/{card['gift_card_id']}"))["balance"], 50)


def test_unknown_gift_card():
    pos.assert_error(pos.get("/gift-cards/99999"), 404, "not found")

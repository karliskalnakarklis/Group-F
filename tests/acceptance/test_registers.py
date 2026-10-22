"""Register sessions and the Z-report."""
import pos

Z_REGISTER = 4      # store 2, used only here
CYCLE_REGISTER = 2  # store 1


def test_open_twice_is_refused():
    pos.open_register(CYCLE_REGISTER)
    pos.assert_error(pos.post(f"/registers/{CYCLE_REGISTER}/open",
                              {"employee_id": pos.CASHIER, "opening_cash": 100}), 409, "register")
    pos.ensure_closed(CYCLE_REGISTER)


def test_close_twice_is_refused():
    pos.open_register(CYCLE_REGISTER)
    pos.ok(pos.post(f"/registers/{CYCLE_REGISTER}/close", {"employee_id": pos.CASHIER, "counted_cash": 100}))
    pos.assert_error(pos.post(f"/registers/{CYCLE_REGISTER}/close",
                              {"employee_id": pos.CASHIER, "counted_cash": 100}), 409, "register")


def test_unknown_register():
    pos.assert_error(pos.post("/registers/999/open", {"employee_id": pos.CASHIER, "opening_cash": 0}),
                     404, "not found")


def test_z_report_matches_the_session():
    pos.open_register(Z_REGISTER, opening_cash=150.0)
    cash_lines = [{"product_id": 5, "qty": 2}, {"product_id": 56, "qty": 1}]
    card_lines = [{"product_id": 30, "qty": 4}]
    cash_sale = pos.ok(pos.sell(Z_REGISTER, cash_lines), 201)
    card_sale = pos.ok(pos.sell(Z_REGISTER, card_lines, method="card"), 201)
    returned = pos.ok(pos.post("/returns", {"sale_id": cash_sale["sale_id"], "register": Z_REGISTER,
                                            "employee_id": pos.CASHIER, "lines": [{"product_id": 5, "qty": 1}]}), 201)

    cash_sales = pos.money(cash_sale["total"])
    refunds = pos.money(returned["refund_amount"])
    expected_cash = pos.money(150) + cash_sales - refunds
    z = pos.ok(pos.post(f"/registers/{Z_REGISTER}/close",
                        {"employee_id": pos.CASHIER, "counted_cash": float(expected_cash - 1)}))
    assert z["sales_count"] == 2
    pos.close_enough(z["gross_total"], pos.money(cash_sale["total"]) + pos.money(card_sale["total"]), "gross_total")
    pos.close_enough(z["tax_total"], pos.money(cash_sale["tax"]) + pos.money(card_sale["tax"]), "tax_total")
    pos.close_enough(z["refunds_total"], refunds, "refunds_total")
    pos.close_enough(z["cash_sales"], cash_sales, "cash_sales")
    pos.close_enough(z["opening_cash"], 150, "opening_cash")
    pos.close_enough(z["cash_expected"], expected_cash, "cash_expected")
    pos.close_enough(z["difference"], -1, "difference")


def test_sales_need_an_open_register():
    pos.open_register(CYCLE_REGISTER)
    pos.ensure_closed(CYCLE_REGISTER)
    pos.assert_error(pos.sell(CYCLE_REGISTER, [{"product_id": 5, "qty": 1}]), 409, "register")

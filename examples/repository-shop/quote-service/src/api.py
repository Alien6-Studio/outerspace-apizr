"""Expose a quote; inventory and pricing stay private implementation support."""

from typing import Literal, TypedDict

from inventory import product
from pricing import discounted, tax


class Line(TypedDict):
    sku: str
    quantity: int


class Order(TypedDict):
    lines: list[Line]
    coupon: Literal["none", "launch"]


def quote(order: Order) -> dict:
    """Quote a fictional EUR order, with stock and a 20% illustrative tax."""
    if not order["lines"]:
        return {"ok": False, "reason": "empty_order"}
    subtotal = 0
    for line in order["lines"]:
        quantity = line["quantity"]
        if quantity < 1:
            return {"ok": False, "reason": "quantity_must_be_positive"}
        try:
            unit_price, stock = product(line["sku"])
        except ValueError:
            return {"ok": False, "reason": "unknown_sku"}
        if quantity > stock:
            return {"ok": False, "reason": "insufficient_stock"}
        subtotal += unit_price * quantity
    net = discounted(subtotal, order["coupon"])
    vat = tax(net)
    return {
        "ok": True,
        "currency": "EUR",
        "net_cents": net,
        "tax_cents": vat,
        "total_cents": net + vat,
    }

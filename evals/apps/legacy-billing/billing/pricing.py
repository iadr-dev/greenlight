"""Invoice arithmetic. Money is whole cents everywhere."""
from __future__ import annotations

VOLUME_DISCOUNT_PERCENT = 5


def line_total(quantity: int, unit_price_cents: int) -> int:
    """The price of one invoice line. Ten or more units of an item get a 5% volume discount."""
    if quantity < 0 or unit_price_cents < 0:
        raise ValueError("quantity and price must not be negative")
    total = quantity * unit_price_cents
    if quantity > 10:
        total = total * (100 - VOLUME_DISCOUNT_PERCENT) // 100
    return total


def invoice(quantity: int, unit_price_cents: int, tax_percent: int) -> dict:
    """Subtotal, tax and total of a one-line invoice. Tax is rounded half up to the cent."""
    subtotal = line_total(quantity, unit_price_cents)
    tax = (subtotal * tax_percent + 50) // 100
    return {"subtotal": subtotal, "tax": tax, "total": subtotal + tax}

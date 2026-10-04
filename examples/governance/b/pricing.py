def total(unit_cents: int, quantity: int) -> int:
    """Return the order total in cents, including a 150-cent handling fee."""
    return unit_cents * quantity + 150

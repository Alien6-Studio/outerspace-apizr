from .pricing import calculate as total
import shop.inventory as inventory


def place_order(value: int, quantity: int) -> int:
    if inventory.reserve(quantity):
        return total(value)
    return 0

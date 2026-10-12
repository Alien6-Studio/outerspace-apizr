"""Integer arithmetic for this educational quote policy."""


def discounted(subtotal: int, coupon: str) -> int:
    return subtotal * 90 // 100 if coupon == "launch" else subtotal


def tax(net: int) -> int:
    return (net * 20 + 50) // 100

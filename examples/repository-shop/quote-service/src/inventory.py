"""Fictional stock and prices in EUR cents; no external data or network."""


def product(sku: str) -> tuple[int, int]:
    catalogue = {"DESK-LAMP": (2500, 12), "NOTEBOOK": (500, 40)}
    if sku not in catalogue:
        raise ValueError("Unknown SKU")
    return catalogue[sku]

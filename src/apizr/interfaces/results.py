"""Bounded finite JSON validation and Python-result transport normalization."""

from apizr.interfaces.json_budget import JSON, JsonBudget


def finite_json_value(value: object) -> JSON:
    """Copy admitted transport JSON without tuples, coercion or unbounded recursion."""
    return JsonBudget().visit(value, copy=True)


def normalize_result_for_json(value: object) -> JSON:
    """Copy bounded finite results and lower Python tuples to JSON arrays."""
    return JsonBudget().visit(value, copy=True, tuples=True)


def normalize_rest_result(value: object) -> JSON:
    """Retain REST's tuple/set lowering within the same finite JSON budget."""
    return JsonBudget().visit(value, copy=True, tuples=True, sets=True)

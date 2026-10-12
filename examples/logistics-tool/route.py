"""Pedagogical nearest-neighbour route over a fictional town."""


def plan_route(stops: list[str]) -> dict:
    """Visit each requested stop once, then return to the warehouse."""
    points = {"warehouse": (0, 0), "library": (2, 0), "cafe": (2, 3), "museum": (0, 4)}
    if not stops or len(stops) != len(set(stops)):
        return {"ok": False, "reason": "provide_unique_stops"}
    if any(stop not in points or stop == "warehouse" for stop in stops):
        return {"ok": False, "reason": "unknown_stop"}
    remaining = sorted(stops)
    route = ["warehouse"]
    minutes = 0
    while remaining:
        current = route[-1]
        next_stop = min(
            remaining, key=lambda stop: (_minutes(points[current], points[stop]), stop)
        )
        minutes += _minutes(points[current], points[next_stop])
        route.append(next_stop)
        remaining.remove(next_stop)
    minutes += _minutes(points[route[-1]], points["warehouse"])
    route.append("warehouse")
    return {"ok": True, "route": route, "estimated_minutes": minutes}


def _minutes(left: tuple[int, int], right: tuple[int, int]) -> int:
    return abs(left[0] - right[0]) + abs(left[1] - right[1])

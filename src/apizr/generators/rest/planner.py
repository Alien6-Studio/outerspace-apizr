"""REST route planning around the shared validated inspection boundary."""

from collections.abc import Sequence

from apizr.inspection import Inspection
from apizr.interfaces.planner import GenerationRefused as GenerationRefused
from apizr.interfaces.planner import plan as interface_plan

from .model import Endpoint, RestPlan


def plan(
    inspection: Inspection,
    source: bytes,
    *,
    executable: bytes | None = None,
    select: Sequence[str] | None = None,
) -> RestPlan:
    contract = interface_plan(inspection, source, executable=executable, select=select)
    return RestPlan(
        **contract.model_dump(exclude={"capabilities"}),
        endpoints=tuple(
            Endpoint(**c.model_dump(), route=f"/capabilities/{c.name}")
            for c in contract.capabilities
        ),
    )

"""Real upstream evidence, never fabricated eligibility."""

import pytest

from apizr.exposure import ExposurePolicy, plan_exposure
from apizr.graph import build_graph
from apizr.repository import scan_sources
from apizr.repository_readiness import RepositoryReadinessPolicy, assess_repository


def evidence(
    sources=None, *, selected=None, modes=("direct",), interfaces=("rest", "mcp")
):
    if sources is None:
        sources = {
            "shop/__init__.py": b'"""A real package initializer."""\n',
            "shop/api.py": b"def run(x: int = 2, /, *, y: int = 3) -> int:\n    return helper(x) + y\n\ndef helper(x: int) -> int:\n    return x * 2\n",
            "shop/pricing.py": b"async def run(x: int) -> int:\n    return x + 1\n",
            "shop/inventory.py": b"def available() -> bool:\n    return True\n",
            "shop/admin.py": b'raise RuntimeError("UNRELATED MUST NOT EXECUTE")\n',
        }
    if selected is None:
        selected = (
            "python:shop.api:run",
            "python:shop.pricing:run",
            "python:shop.inventory:available",
        )
    catalog = scan_sources(sources.items())
    graph = build_graph(catalog, sources)
    readiness = assess_repository(
        catalog,
        graph,
        policy=RepositoryReadinessPolicy.model_validate(
            {"execution": {"modes": modes}}
        ),
    )
    policy = ExposurePolicy.model_validate(
        {
            "selection": {"include": selected},
            "interfaces": interfaces,
            "execution": {"allowed": modes},
        }
    )
    exposure = plan_exposure(catalog, graph, readiness, policy=policy)
    return catalog, graph, readiness, policy, exposure, sources


@pytest.fixture
def inputs():
    return evidence()

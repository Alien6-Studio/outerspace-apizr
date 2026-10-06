"""Real generated stdio clients and REST business parity across runtime owners."""

import json
import sys
from importlib.resources import files

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client, StdioServerParameters
from repository_interfaces.conftest import evidence

from apizr.execution import ExecutionPolicy
from apizr.generators.mcp import generate as mcp_generate
from apizr.generators.rest import generate as rest_generate
from apizr.generators.rest.runtime import create_app as direct_rest
from apizr.governed.rest import create_app as local_rest
from apizr.governed_oci.rest import create_app as oci_rest
from apizr.governed_repository.rest import create_app as repository_governed_rest
from apizr.inspection import inspect_source
from apizr.oci.model import ExecutionPolicyV2
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_interfaces.rest_runtime import create_app as repository_rest

pytestmark = pytest.mark.timeout(180)

SOURCE = b"""def tuple_result():
    return ([12, 15, 15], [8, 8, 9])
def nested_tuple_result():
    return {"support": ("61.8%", 10.674), "bands": ([1, 2], (3, 4))}
def typed_tuple_result() -> tuple[list[int], list[int]]:
    return ([12, 15, 15], [8, 8, 9])
def variadic_tuple_result() -> tuple[int, ...]:
    return (3, 1, 2)
async def async_result():
    return [(True, None, 2.5, "s")]
def object_result():
    return {"result": (1, 2), "other": [False]}
def annotation_is_not_enforced() -> int:
    return (1, 2)
def reconstructed(x: tuple[int, str], values: set[int]):
    return (isinstance(x, tuple), isinstance(values, set), x, sorted(values))
def counter(default: list[int] = []):
    default.append(1)
    return (len(default),)
def invalid(kind: int):
    if kind == 0: return {"nested": (float("nan"),)}
    if kind == 1: return {"nested": (float("inf"),)}
    if kind == 2: return {"nested": (float("-inf"),)}
    if kind == 3: return {"nested": (object(),)}
    if kind == 4: return {1: (1, 2)}
    if kind == 5: return {"nested": (complex(1, 2),)}
    if kind == 6: return {"nested": ({1, 2},)}
    result = []
    result.append(result)
    return result
"""
CASES = [
    ("tuple_result", {}, [[12, 15, 15], [8, 8, 9]]),
    (
        "nested_tuple_result",
        {},
        {"support": ["61.8%", 10.674], "bands": [[1, 2], [3, 4]]},
    ),
    ("typed_tuple_result", {}, [[12, 15, 15], [8, 8, 9]]),
    ("variadic_tuple_result", {}, [3, 1, 2]),
    ("async_result", {}, [[True, None, 2.5, "s"]]),
    ("object_result", {}, {"result": [1, 2], "other": [False]}),
    ("annotation_is_not_enforced", {}, [1, 2]),
    (
        "reconstructed",
        {"x": [1, "a"], "values": [3, 1]},
        [True, True, [1, "a"], [1, 3]],
    ),
]


def generated(root, *, repository, backend, image, transport):
    policy = (
        None
        if backend == "direct"
        else (ExecutionPolicyV2() if image else ExecutionPolicy())
    )
    if repository:
        inputs = evidence(
            {"tuple_sample.py": SOURCE},
            selected=tuple(
                "python:tuple_sample:" + name
                for name in [*(name for name, _, _ in CASES), "counter", "invalid"]
            ),
            modes=(backend,),
            interfaces=(transport,),
        )
        write_bundle(
            root,
            render_repository_bundle(
                *inputs,
                interface=transport,
                execution_policy=policy,
                runtime_image=image,
            ),
        )
    else:
        generate = rest_generate if transport == "rest" else mcp_generate
        generate(
            inspect_source(SOURCE, module_name="tuple_sample"),
            SOURCE,
            root,
            execution_policy=policy,
            runtime_image=image,
        )


@pytest.mark.parametrize("repository", [False, True])
@pytest.mark.parametrize("backend", ["direct", "local-process", "oci-container"])
@pytest.mark.parametrize("protocol", ["auto", "legacy"])
def test_tuple_business_parity_over_real_generated_stdio(
    tmp_path,
    request,
    repository,
    backend,
    protocol,
):
    image = (
        request.getfixturevalue("worker_image") if backend == "oci-container" else None
    )
    rest = tmp_path / "rest"
    mcp = tmp_path / "mcp"
    for transport, root in (("rest", rest), ("mcp", mcp)):
        generated(
            root,
            repository=repository,
            backend=backend,
            image=image,
            transport=transport,
        )
    prefix = "tuple_sample." if repository else ""
    if repository:
        app = (repository_rest if backend == "direct" else repository_governed_rest)(
            rest
        )
    elif backend == "direct":
        manifest = json.loads((rest / "apizr-rest.json").read_bytes())
        app = direct_rest(rest, {**manifest, "endpoints": manifest["capabilities"]})
    else:
        app = (oci_rest if image else local_rest)(rest)
    try:
        with TestClient(app) as client:
            business = {}
            for name, arguments, expected in CASES:
                response = client.post("/capabilities/" + prefix + name, json=arguments)
                assert response.status_code == 200 and response.json() == expected
                business[name] = response.json()

        async def probe():
            target = StdioServerParameters(
                command=sys.executable,
                args=[str(mcp / "server.py")],
                cwd=mcp,
            )
            async with Client(target, mode=protocol, read_timeout_seconds=20) as client:
                assert client.protocol_version == (
                    "2025-11-25" if protocol == "legacy" else "2026-07-28"
                )
                tools = (await client.list_tools()).tools
                assert {t.name for t in tools} == {
                    prefix + n for n in [*business, "counter", "invalid"]
                }
                assert all(t.output_schema is None for t in tools)
                for name, arguments, _ in CASES:
                    result = await client.call_tool(prefix + name, arguments)
                    expected = business[name]
                    structured = (
                        expected if isinstance(expected, dict) else {"result": expected}
                    )
                    assert (
                        not result.is_error and result.structured_content == structured
                    )
                    assert len(result.content) == 1 and result.content[0].type == "text"
                    assert json.loads(result.content[0].text) == structured
                for expected in ([1], [2] if backend == "direct" else [1]):
                    result = await client.call_tool(prefix + "counter", {})
                    assert not result.is_error and result.structured_content == {
                        "result": expected
                    }
                for kind in range(8):
                    result = await client.call_tool(prefix + "invalid", {"kind": kind})
                    assert result.is_error and result.structured_content is None
                    assert result.content[0].text == "Tool execution failed"
                    assert len(result.content) == 1
                    # A cyclic or otherwise invalid result must not kill the session.
                    recovered = await client.call_tool(prefix + "tuple_result", {})
                    assert not recovered.is_error

        anyio.run(probe)
    finally:
        sys.modules.pop("tuple_sample", None)
        if repository and backend == "direct":
            from apizr.repository_interfaces.runtime import RepositoryLoader

            for finder in list(sys.meta_path):
                if isinstance(finder, RepositoryLoader):
                    finder.close()
    # Generated bundles copy the exact reviewed semantic implementation, not a fork.
    reviewed = files("apizr.interfaces").joinpath("results.py").read_text()
    if backend == "direct":
        expected_source = reviewed.replace(
            "from apizr.interfaces.runtime import", "from apizr_runtime import"
        )
        assert (mcp / "apizr_results.py").read_text() == expected_source
    else:
        expected_source = reviewed.replace("from apizr.", "from apizr_governed.")
        assert (
            mcp / "apizr_governed/interfaces/results.py"
        ).read_text() == expected_source
        assert not (mcp / "apizr_results.py").exists()
    assert "outerspace-apizr" not in (mcp / "requirements.txt").read_text()

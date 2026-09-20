import json
from pathlib import Path

import anyio
import nbformat
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from mcp import Client

from apizr.cli import main
from apizr.execution import ExecutionPolicy
from apizr.execution.model import ExecutionResult
from apizr.execution.protocol import encode
from apizr.generators.mcp import render as mcp_render
from apizr.generators.rest import render as rest_render
from apizr.governed.mcp import create_server
from apizr.governed.rest import create_app
from apizr.governed.runtime import GovernedRuntime
from apizr.inspection import inspect_source

from .helpers import bundle

pytestmark = pytest.mark.timeout(30)


@pytest.mark.parametrize("transport", ["rest", "mcp"])
@pytest.mark.parametrize("notebook", [False, True])
def test_cli_selection_modes_and_notebook_runtime(
    tmp_path, capsys, transport, notebook
):
    source = tmp_path / ("sample.ipynb" if notebook else "sample.py")
    code = "def f(x: int=1): return x\ndef unused(): return 7\n"
    if notebook:
        nbformat.write(
            nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code)]), source
        )
    else:
        source.write_text(code)
    policy = tmp_path / "policy.json"
    policy.write_text("{}")
    for governed in [False, True]:
        root = tmp_path / str(governed)
        argv = [
            "generate",
            transport,
            str(source),
            "--select",
            "f",
            "--output-dir",
            str(root),
        ]
        if governed:
            argv += ["--execution-policy", str(policy)]
        assert main(argv) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["execution"]["mode"] == ("governed" if governed else "direct")
        if governed:
            runtime = GovernedRuntime(root, transport)
            assert list(runtime.plans) == ["python:sample:f"]
            assert runtime.invoke("python:sample:f", {}).value == 1
        else:
            assert not (root / "execution").exists()
    policy.write_text('{"network":{"mode":"deny"}}')
    assert (
        main(
            [
                "generate",
                transport,
                str(source),
                "--output-dir",
                str(tmp_path / "refused"),
                "--execution-policy",
                str(policy),
            ]
        )
        == 2
    )
    assert not (tmp_path / "refused").exists()
    assert "unsupported_control" in capsys.readouterr().err


@settings(max_examples=3, deadline=None)
@given(st.integers(0, 250))
def test_embedded_output_boundary_property(tmp_path_factory, count):
    source = f'def f(): return "x"*{count}'.encode()
    limit = 128
    expected = (
        len(
            encode(
                ExecutionResult(status="success", value="x" * count).model_dump(
                    mode="json"
                ),
                10000,
            )
        )
        <= limit
    )
    for transport in ["rest", "mcp"]:
        root = bundle(
            tmp_path_factory.mktemp("boundary") / "bundle",
            transport,
            source=source,
            policy=ExecutionPolicy.model_validate(
                {"limits": {"max_output_bytes": limit}}
            ),
        )
        if transport == "rest":
            with TestClient(create_app(root)) as client:
                assert client.post("/capabilities/f", json={}).status_code == (
                    200 if expected else 500
                )
        else:

            async def check(root=root):
                async with Client(create_server(root)) as client:
                    assert (await client.call_tool("f", {})).is_error != expected

            anyio.run(check)


@settings(max_examples=3, deadline=None)
@given(st.lists(st.sampled_from(["APIZR_TEST_SECRET", "LANG", "TZ"]), max_size=5))
def test_embedded_allowlist_property(tmp_path_factory, names):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("APIZR_TEST_SECRET", "env-value-not-in-artifacts")
        source = b'import os\ndef f(): return "APIZR_TEST_SECRET" in os.environ'
        policy = ExecutionPolicy.model_validate({"environment": {"allow": names}})
        for transport in ["rest", "mcp"]:
            root = bundle(
                tmp_path_factory.mktemp("allowlist") / "bundle",
                transport,
                source=source,
                policy=policy,
            )
            runtime = GovernedRuntime(root, transport)
            assert runtime.invoke("python:governed_sample:f", {}).value == (
                "APIZR_TEST_SECRET" in names
            )
            assert all(
                b"env-value-not-in-artifacts" not in p.read_bytes()
                for p in root.rglob("*")
                if p.is_file()
            )


@pytest.mark.parametrize(
    "transport,render", [("rest", rest_render), ("mcp", mcp_render)]
)
def test_governed_golden_is_stable_across_python_and_directories(
    tmp_path, transport, render
):
    source = b"def f(a: int, /, *, b: int=2): return a+b\n"
    inspected = inspect_source(source, module_name="golden.governed")
    artifacts = render(inspected, source, execution_policy=ExecutionPolicy())
    expected = (
        Path(__file__).parents[1] / "fixtures/governed" / f"{transport}-manifest.json"
    )
    assert artifacts[f"apizr-{transport}.json"] == expected.read_bytes()
    from apizr.interfaces.output import write_bundle

    roots = [tmp_path / "first", tmp_path / "unrelated/nested"]
    for root in roots:
        write_bundle(
            root, render(inspected, source, execution_policy=ExecutionPolicy())
        )
    for name in artifacts:
        assert (roots[0] / name).read_bytes() == (roots[1] / name).read_bytes()

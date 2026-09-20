import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import anyio
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from mcp import Client

from apizr.generators.mcp import generate, render
from apizr.generators.mcp.runtime import create_server
from apizr.inspection import inspect_source
from apizr.interfaces.planner import GenerationRefused

from .helpers import server_bundle


@settings(max_examples=20, deadline=None)
@given(st.integers(), st.text(max_size=20))
def test_complete_artifact_determinism(default, description):
    source = f"def f(x: int = {default}):\n    {description!r}\n    return x\n".encode()
    inspection = inspect_source(source, module_name="stable.module")
    with TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        contents = []
        for path in [root / "a", root / "unrelated/b"]:
            generate(inspection, source, path)
            contents.append(
                {
                    f.relative_to(path).as_posix(): f.read_bytes()
                    for f in path.rglob("*")
                    if f.is_file()
                }
            )
        assert contents[0] == contents[1] == render(inspection, source)


@settings(max_examples=25, deadline=None)
@given(st.integers(-100, 100), st.integers(-100, 100), st.booleans(), st.booleans())
def test_argument_reconstruction_and_null_validation(a, b, supplied, explicit_null):
    source = "def f(a: int, /, *, b: int = 2): return [a,b]"
    payload = {"a": a}
    if supplied:
        payload["b"] = None if explicit_null else b

    async def check(server):
        async with Client(server) as client:
            result = await client.call_tool("f", payload)
            assert result.is_error == (supplied and explicit_null)
            if not result.is_error:
                assert result.structured_content == [a, b if supplied else 2]

    with TemporaryDirectory() as directory:
        with server_bundle(Path(directory).resolve() / "bundle", source) as (server, _):
            anyio.run(check, server)


@settings(max_examples=20, deadline=None)
@given(st.binary(min_size=1, max_size=40))
def test_mutated_source_fails_before_import(mutation):
    source = b"def f(): return 1"
    with TemporaryDirectory() as directory:
        root = Path(directory).resolve() / "bundle"
        generate(inspect_source(source, module_name="mutation_probe"), source, root)
        (root / "source/mutation_probe.py").write_bytes(source + mutation)
        with pytest.raises(RuntimeError, match="digest mismatch"):
            create_server(root, json.loads((root / "apizr-mcp.json").read_bytes()))
        assert "mutation_probe" not in sys.modules


@settings(max_examples=20, deadline=None)
@given(st.sets(st.sampled_from(["a", "b", "c"]), min_size=1))
def test_selection_only_advertises_selected_ready_tools(selected):
    source = b"def a(): pass\ndef b(): pass\ndef c(): pass\ndef stream(): yield 1"
    inspection = inspect_source(source, module_name="selection")
    artifacts = render(inspection, source, select=sorted(selected))
    assert {
        t["name"] for t in json.loads(artifacts["mcp-tools.json"])["tools"]
    } == selected
    with pytest.raises(GenerationRefused):
        render(inspection, source, select=[*selected, "stream"])


@settings(max_examples=20, deadline=None)
@given(
    st.sampled_from(["decorator", "annotation", "default", "assignment", "earlier"]),
    st.integers(),
)
def test_hostile_source_expressions_remain_inert(phase, value):
    with TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        marker = root / "executed"
        expression = f"(__import__('pathlib').Path({str(marker)!r}).touch(), __import__('os').environ.__setitem__('MCP_EXECUTED', {str(value)!r}))"
        code = {
            "decorator": f"@{expression}\ndef f(): pass",
            "annotation": f"def f(x: {expression}): pass",
            "default": f"def f(x={expression}): pass",
            "assignment": f"def f(): pass\nf={expression}",
            "earlier": f"{expression}\ndef f(): pass",
        }[phase].encode()
        before = dict(os.environ)
        with pytest.raises(GenerationRefused):
            generate(inspect_source(code, module_name="hostile"), code, root / "bundle")
        assert not marker.exists() and not (root / "bundle").exists()
        assert before == dict(os.environ)

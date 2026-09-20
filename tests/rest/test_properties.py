import builtins
import importlib.util
import json
import os
import socket
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from apizr.generators.rest import generate, render
from apizr.generators.rest.planner import GenerationRefused
from apizr.inspection import inspect_source

from .helpers import application

SCALARS = (
    st.none()
    | st.booleans()
    | st.integers(min_value=-1000, max_value=1000)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=15)
)
JSON_VALUES = st.recursive(
    SCALARS,
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(st.text(max_size=8), children, max_size=4)
    ),
    max_leaves=10,
)


@settings(max_examples=25, deadline=None, print_blob=True)
@given(st.integers(), st.text(max_size=20))
def test_artifacts_are_identical_across_unrelated_output_directories(
    default, description
):
    # repr makes arbitrary text a safe, exact Python docstring declaration.
    source = f"def f(x: int = {default}) -> int:\n    {description!r}\n    return x\n".encode()
    inspection = inspect_source(source, module_name="stable.module")
    with TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        a, b = root / "first", root / "unrelated" / "second"
        generate(inspection, source, a)
        generate(inspection, source, b)

        def contents(path):
            return {
                str(p.relative_to(path)): p.read_bytes()
                for p in path.rglob("*")
                if p.is_file()
            }

        assert contents(a) == contents(b) == render(inspection, source)


@settings(max_examples=30, deadline=None, print_blob=True)
@given(
    st.integers(-100, 100),
    st.integers(-100, 100),
    st.integers(-100, 100),
    st.booleans(),
    st.booleans(),
)
def test_generated_adapter_preserves_positional_and_keyword_binding(
    a, b, c, include_b, include_c
):
    source = "def f(a: int, /, b: int = 2, *, c: int = 3): return [a, b, c]\n"
    payload = {"a": a}
    if include_b:
        payload["b"] = b
    if include_c:
        payload["c"] = c
    with TemporaryDirectory() as directory:
        with application(Path(directory).resolve() / "bundle", source) as adapter:
            response = TestClient(adapter.app).post("/capabilities/f", json=payload)
            assert response.status_code == 200
            assert response.json() == [a, b if include_b else 2, c if include_c else 3]


@settings(max_examples=50, deadline=None, print_blob=True)
@given(JSON_VALUES)
def test_random_request_validation_matches_published_integer_contract(value):
    with TemporaryDirectory() as directory:
        with application(
            Path(directory).resolve() / "bundle", "def f(x: int): return x"
        ) as adapter:
            client = TestClient(adapter.app)
            schema = client.get("/openapi.json").json()["paths"]["/capabilities/f"][
                "post"
            ]["requestBody"]["content"]["application/json"]["schema"]
            payload = {"x": value}
            response = client.post("/capabilities/f", json=payload)
            assert (response.status_code == 200) == Draft202012Validator(
                schema
            ).is_valid(payload)
            if response.status_code == 200:
                assert response.json() == value


@settings(max_examples=25, deadline=None, print_blob=True)
@given(
    st.sampled_from(["decorator", "default", "annotation", "assignment", "earlier"]),
    st.integers(),
)
def test_hostile_declarations_cannot_execute_during_generation(phase, number):
    with TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        marker = root / "executed"
        expression = f"(__import__('pathlib').Path({str(marker)!r}).touch(), __import__('os').environ.__setitem__('REST_EXECUTED', {str(number)!r}))"
        forms = {
            "decorator": f"@{expression}\ndef f(): pass",
            "default": f"def f(x={expression}): pass",
            "annotation": f"def f(x: {expression}): pass",
            "assignment": f"def f(): pass\nf={expression}",
            "earlier": f"{expression}\ndef f(): pass",
        }
        source = forms[phase].encode()
        environment = dict(os.environ)
        original_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            assert name != "hostile_contract"
            return original_import(name, *args, **kwargs)

        def forbidden(*args, **kwargs):
            raise AssertionError("Generation attempted runtime I/O")

        with (
            patch.object(builtins, "__import__", guarded),
            patch.object(socket.socket, "connect", forbidden),
            patch.object(subprocess, "Popen", forbidden),
            patch.object(os, "system", forbidden),
        ):
            inspected = inspect_source(source, module_name="hostile_contract")
            with pytest.raises(GenerationRefused):
                generate(inspected, source, root / "output")
        assert not marker.exists()
        assert not (root / "output").exists()
        assert dict(os.environ) == environment


@settings(max_examples=20, deadline=None, print_blob=True)
@given(st.binary(min_size=1, max_size=30))
def test_every_sampled_source_mutation_is_detected_before_import(mutation):
    source = b"def f(): return 1\n"
    with TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        generate(inspect_source(source, module_name="mutated"), source, root / "bundle")
        (root / "bundle/source/mutated.py").write_bytes(source + mutation)
        spec = importlib.util.spec_from_file_location(
            "mutated_adapter", root / "bundle/app.py"
        )
        module = importlib.util.module_from_spec(spec)
        with pytest.raises(RuntimeError, match="source digest mismatch"):
            spec.loader.exec_module(module)


@settings(max_examples=20, deadline=None, print_blob=True)
@given(st.sets(st.sampled_from(["a", "b", "c"]), min_size=1))
def test_only_selected_ready_capabilities_are_exposed(selected):
    source = b"def a(): return 1\ndef b(): return 2\ndef c(): return 3\ndef stream(): yield 4\n"
    inspected = inspect_source(source, module_name="selected")
    artifacts = render(inspected, source, select=sorted(selected))
    paths = json.loads(artifacts["openapi.json"])["paths"]
    assert set(paths) == {"/health"} | {"/capabilities/" + name for name in selected}
    with pytest.raises(GenerationRefused):
        render(inspected, source, select=[*sorted(selected), "stream"])

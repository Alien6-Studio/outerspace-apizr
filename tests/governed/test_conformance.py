import json
import sys

import anyio
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from mcp import Client

from apizr.execute_cli import main as execute_cli
from apizr.execution import ExecutionPolicy
from apizr.generators.mcp import generate as generate_mcp
from apizr.generators.mcp.runtime import create_server as direct_mcp
from apizr.generators.rest import generate as generate_rest
from apizr.generators.rest.runtime import create_app as direct_rest
from apizr.governed.mcp import create_server as governed_mcp
from apizr.governed.rest import create_app as governed_rest
from apizr.inspection import inspect_source

from .helpers import SOURCE, bundle, manifest

pytestmark = pytest.mark.timeout(60)

# One reviewed corpus is run against all five entry points.
CORPUS = [
    ("total", {"a": 1}, True, 6),
    ("total", {"a": 1, "b": 4, "c": 5}, True, 10),
    ("greet", {"name": "Ada"}, True, "Hello Ada"),
    ("nullable", {}, True, None),
    ("nullable", {"x": None}, True, None),
    ("default_null", {}, True, None),
    ("default_null", {"x": None}, False, None),
    ("total", {}, False, None),
    ("total", {"a": True}, False, None),
    ("total", {"a": 1, "extra": 2}, False, None),
]


def test_shared_five_backend_conformance(tmp_path, capsys):
    roots = {}
    for mode in ["direct", "governed"]:
        for transport, generate in [("rest", generate_rest), ("mcp", generate_mcp)]:
            root = tmp_path / (mode + "-" + transport)
            generate(
                inspect_source(SOURCE, module_name="conformance"),
                SOURCE,
                root,
                execution_policy=ExecutionPolicy() if mode == "governed" else None,
            )
            roots[mode, transport] = root

    async def check_mcp(server):
        async with Client(server) as client:
            for name, args, valid, value in CORPUS:
                result = await client.call_tool(name, args)
                assert result.is_error != valid
                if valid:
                    assert result.structured_content == value

    try:
        for mode in ["direct", "governed"]:
            root = roots[mode, "rest"]
            doc = manifest(root, "rest")
            app = (
                direct_rest(root, {**doc, "endpoints": doc["capabilities"]})
                if mode == "direct"
                else governed_rest(root)
            )
            with TestClient(app) as client:
                for name, args, valid, value in CORPUS:
                    response = client.post("/capabilities/" + name, json=args)
                    assert response.status_code == (200 if valid else 422)
                    if valid:
                        assert response.json() == value
            sys.modules.pop("conformance", None)
            root = roots[mode, "mcp"]
            server = (
                direct_mcp(root, manifest(root, "mcp"))
                if mode == "direct"
                else governed_mcp(root)
            )
            anyio.run(check_mcp, server)
            sys.modules.pop("conformance", None)
        source = tmp_path / "source.py"
        source.write_bytes(SOURCE)
        policy = tmp_path / "policy.json"
        policy.write_text("{}")
        args_file = tmp_path / "args.json"
        for name, args, valid, value in CORPUS:
            args_file.write_text(json.dumps(args))
            code = execute_cli(
                [
                    str(source),
                    name,
                    "--arguments",
                    str(args_file),
                    "--policy",
                    str(policy),
                ]
            )
            assert code == (0 if valid else 1)
            result = json.loads(capsys.readouterr().out)
            if valid:
                assert result["value"] == value
    finally:
        sys.modules.pop("conformance", None)


@pytest.mark.parametrize("mode", ["direct", "governed"])
def test_state_lifetime_is_explicit(tmp_path, mode):
    root = tmp_path / "rest"
    generate_rest(
        inspect_source(SOURCE, module_name="state_lifetime"),
        SOURCE,
        root,
        execution_policy=ExecutionPolicy() if mode == "governed" else None,
    )
    doc = manifest(root, "rest")
    app = (
        direct_rest(root, {**doc, "endpoints": doc["capabilities"]})
        if mode == "direct"
        else governed_rest(root)
    )
    try:
        with TestClient(app) as client:
            assert client.post("/capabilities/counter", json={}).json() == [1, 1]
            assert client.post("/capabilities/counter", json={}).json() == (
                [2, 2] if mode == "direct" else [1, 1]
            )
        sys.modules.pop("state_lifetime", None)
        root = tmp_path / "mcp"
        generate_mcp(
            inspect_source(SOURCE, module_name="state_lifetime"),
            SOURCE,
            root,
            execution_policy=ExecutionPolicy() if mode == "governed" else None,
        )
        server = (
            direct_mcp(root, manifest(root, "mcp"))
            if mode == "direct"
            else governed_mcp(root)
        )

        async def check():
            async with Client(server) as client:
                assert (await client.call_tool("counter", {})).structured_content == [
                    1,
                    1,
                ]
                assert (await client.call_tool("counter", {})).structured_content == (
                    [2, 2] if mode == "direct" else [1, 1]
                )

        anyio.run(check)
    finally:
        sys.modules.pop("state_lifetime", None)


@settings(max_examples=3, deadline=None)
@given(st.integers(-100, 100), st.booleans())
def test_argument_parity_property(tmp_path_factory, value, supply):
    root = tmp_path_factory.mktemp("parity")
    source = b"def f(a: int, /, *, b: int=3): return a+b"
    payload = {"a": value, **({"b": value} if supply else {})}
    expected = value + (value if supply else 3)

    async def mcp_call(server):
        async with Client(server) as client:
            assert (await client.call_tool("f", payload)).structured_content == expected

    for governed in [False, True]:
        policy = ExecutionPolicy() if governed else None
        for target, generate in [("rest", generate_rest), ("mcp", generate_mcp)]:
            output = root / (target + str(governed))
            generate(
                inspect_source(source, module_name="property_sample"),
                source,
                output,
                execution_policy=policy,
            )
            try:
                doc = manifest(output, target)
                if target == "rest":
                    app = (
                        governed_rest(output)
                        if governed
                        else direct_rest(
                            output, {**doc, "endpoints": doc["capabilities"]}
                        )
                    )
                    with TestClient(app) as client:
                        assert (
                            client.post("/capabilities/f", json=payload).json()
                            == expected
                        )
                else:
                    anyio.run(
                        mcp_call,
                        governed_mcp(output) if governed else direct_mcp(output, doc),
                    )
            finally:
                sys.modules.pop("property_sample", None)


def test_environment_allowlist_and_strict_rest_output(tmp_path, monkeypatch):
    monkeypatch.setenv("APIZR_TEST_SECRET", "env-only-marker-2984")
    policy = ExecutionPolicy.model_validate(
        {"environment": {"allow": ["APIZR_TEST_SECRET"]}}
    )
    for transport in ["rest", "mcp"]:
        root = bundle(tmp_path / transport, transport, policy=policy)
        assert all(
            b"env-only-marker-2984" not in p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        )
        if transport == "rest":
            with TestClient(governed_rest(root)) as client:
                assert client.post("/capabilities/environment", json={}).json() is True
        else:

            async def check(root=root):
                async with Client(governed_mcp(root)) as client:
                    assert (
                        await client.call_tool("environment", {})
                    ).structured_content is True

            anyio.run(check)
    source = b"def f(): return (1,2)"
    for governed in [False, True]:
        root = tmp_path / str(governed)
        generate_rest(
            inspect_source(source, module_name="result_sample"),
            source,
            root,
            execution_policy=ExecutionPolicy() if governed else None,
        )
        doc = manifest(root, "rest")
        app = (
            governed_rest(root)
            if governed
            else direct_rest(root, {**doc, "endpoints": doc["capabilities"]})
        )
        try:
            with TestClient(app) as client:
                result = client.post("/capabilities/f", json={})
                assert result.status_code == (500 if governed else 200)
                if not governed:
                    assert result.json() == [1, 2]
        finally:
            sys.modules.pop("result_sample", None)

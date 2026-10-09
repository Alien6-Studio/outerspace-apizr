import json
import sys
from importlib.resources import files

import anyio
import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st
from mcp import Client, StdioServerParameters
from rest.helpers import application

from apizr.client_collections.planner import example_value, plan_client_collection
from apizr.contract_types import ObjectField, TypeSpec
from apizr.generators.mcp.generator import generate as mcp_generate
from apizr.generators.rest.generator import generate as rest_generate
from apizr.inspection import inspect_source
from apizr.interfaces.runtime import validate

from .test_static import MINIMAL, MINIMAL_SCHEMA, NESTED

INVALID_MINIMAL = [
    {},
    {"value": "3"},
    {"value": True},
    {"value": 1.5},
    {"value": 3, "extra": 1},
    [],
    None,
]
INVALID_NESTED = [
    {},
    {"customer_id": "c"},
    {"customer_id": "c", "features": {}},
    {"customer_id": "c", "features": {"age": "2", "score": 3}},
    {"customer_id": "c", "features": {"age": 2, "score": True}},
    {"customer_id": "c", "features": {"age": 2, "score": 3, "extra": 1}},
    {"customer_id": "c", "features": {"age": 2, "score": 3}, "extra": 1},
]


@pytest.mark.parametrize(
    "source,name,payload,expected,invalid",
    [
        (MINIMAL, "calculate", {"value": 3}, 6, INVALID_MINIMAL),
        (
            NESTED,
            "predict",
            {"customer_id": "c", "features": {"age": 2, "score": 3}},
            6.0,
            INVALID_NESTED,
        ),
    ],
)
def test_real_http_contract_and_invalid_requests(
    tmp_path, source, name, payload, expected, invalid
):
    with application(tmp_path / "rest", source) as adapter:
        with TestClient(adapter.app) as client:
            path = "/capabilities/" + name
            response = client.post(path, json={"payload": payload})
            assert response.status_code == 200 and response.json() == expected
            for value in invalid:
                response = client.post(path, json={"payload": value})
                assert response.status_code == 422 and isinstance(
                    response.json()["detail"], str
                )
            if source == MINIMAL:
                schema = client.get("/openapi.json").json()["paths"][path]["post"][
                    "requestBody"
                ]["content"]["application/json"]["schema"]
                assert schema["properties"]["payload"] == MINIMAL_SCHEMA


@pytest.mark.parametrize(
    "source,name,payload,expected,invalid",
    [
        (MINIMAL, "calculate", {"value": 3}, 6, INVALID_MINIMAL),
        (
            NESTED,
            "predict",
            {"customer_id": "c", "features": {"age": 2, "score": 3}},
            6.0,
            INVALID_NESTED,
        ),
    ],
)
def test_official_sdk_real_stdio_schema_success_and_failure(
    tmp_path, source, name, payload, expected, invalid
):
    root = tmp_path / "mcp"
    raw = source.encode()
    mcp_generate(inspect_source(raw, module_name="typed_stdio"), raw, root)
    assert (root / "apizr_runtime.py").read_bytes() == files(
        "apizr.interfaces"
    ).joinpath("runtime.py").read_bytes()

    async def check():
        async with Client(
            StdioServerParameters(
                command=sys.executable, args=[str(root / "server.py")]
            ),
            read_timeout_seconds=10,
        ) as client:
            tools = (await client.list_tools()).tools
            assert len(tools) == 1 and tools[0].name == name
            assert tools[0].output_schema is None
            if source == MINIMAL:
                assert tools[0].input_schema == {
                    "type": "object",
                    "properties": {"payload": MINIMAL_SCHEMA},
                    "required": ["payload"],
                    "additionalProperties": False,
                }
            result = await client.call_tool(name, {"payload": payload})
            assert result.is_error is False and result.structured_content == {
                "result": expected
            }
            assert json.loads(result.content[0].text) == result.structured_content
            for value in invalid:
                result = await client.call_tool(name, {"payload": value})
                assert result.is_error is True and result.structured_content is None
                assert result.content[0].text == "Invalid tool arguments"

    anyio.run(check)


def test_optional_fields_and_plain_dictionary_reconstruction():
    inspected = inspect_source(NESTED, module_name="typed")
    shape = inspected.readiness.structured_types[1].type
    spec = shape.model_dump(mode="json")
    source = {"customer_id": "c", "features": {"age": 2.0, "score": 3}}
    converted = validate(source, spec)
    assert type(converted) is dict and type(converted["features"]) is dict
    assert converted is not source and converted["features"] is not source["features"]
    assert (
        type(converted["features"]["age"]) is int
        and type(converted["features"]["score"]) is float
    )
    assert "note" not in converted
    assert validate({**source, "note": "hello"}, spec)["note"] == "hello"
    with pytest.raises(ValueError):
        validate({**source, "note": None}, spec)
    with pytest.raises(ValueError, match="fields are missing"):
        validate({}, {"kind": "object", "items": [], "values": [], "variadic": False})
    assert validate({}, TypeSpec(kind="object").model_dump(mode="json")) == {}


@pytest.mark.parametrize("source", [MINIMAL, NESTED])
def test_clients_use_shared_schema_and_structured_example(tmp_path, source):
    raw = source.encode()
    root = tmp_path / "rest"
    rest_generate(inspect_source(raw, module_name="typed_clients"), raw, root)
    collection = plan_client_collection(root)
    request = collection.requests[0]
    expected = (
        {"payload": {"value": 0}}
        if source == MINIMAL
        else {"payload": {"customer_id": "", "features": {"age": 0, "score": 0.0}}}
    )
    assert request.example == expected
    assert (
        request.request_schema["properties"]["payload"]["additionalProperties"] is False
    )
    shape = (
        inspect_source(raw, module_name="typed_clients")
        .readiness.structured_types[-1]
        .type
    )
    assert example_value(shape) == expected["payload"]


@given(st.booleans(), st.integers(), st.permutations(["a", "z"]))
def test_required_extra_fields_and_mapping_order(required, value, order):
    spec = TypeSpec(
        kind="object",
        fields=tuple(
            ObjectField(name=name, required=required, type=TypeSpec(kind="int"))
            for name in order
        ),
    ).model_dump(mode="json")
    payload = dict.fromkeys(order, value)
    assert validate(payload, spec) == payload
    if required:
        with pytest.raises(ValueError, match="Missing required"):
            validate({"a": value}, spec)
    else:
        assert validate({}, spec) == {}
    with pytest.raises(ValueError, match="Unexpected"):
        validate({**payload, "extra": value}, spec)
    with pytest.raises(ValueError):
        validate({"a": str(value)}, spec)

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from .helpers import application


@pytest.mark.parametrize(
    ("annotation", "value", "expected"),
    [
        ("int", 2, 2),
        ("int", 2.0, 2),
        ("str", "hi", "hi"),
        ("float", 2, 2.0),
        ("bool", True, True),
        ("None", None, None),
        ("Any", {"a": [1, None]}, {"a": [1, None]}),
        ("list[int]", [1, 2], [1, 2]),
        ("dict[str, int]", {"x": 1}, {"x": 1}),
        ("tuple[int, str]", [1, "x"], [1, "x"]),
        ("tuple[int, ...]", [1, 2], [1, 2]),
        ("tuple[()]", [], []),
        ("set[int]", [1], [1]),
        ("int | str", "x", "x"),
        ("Union[int, str]", 1, 1),
        ("Optional[int]", None, None),
        ("Literal[-1, 'x', True, None]", -1, -1),
        ("Literal[-1, 'x', True, None]", True, True),
        ("Literal[-1.5]", -1.5, -1.5),
        ("list", [1, "x"], [1, "x"]),
        ("dict", {"a": 1}, {"a": 1}),
        ("tuple", [1, "x"], [1, "x"]),
        ("set", [1], [1]),
        ("typing.List[int]", [1], [1]),
    ],
)
def test_ready_input_contracts_validate_and_reconstruct_types(
    tmp_path, annotation, value, expected
):
    source = f"from __future__ import annotations\ndef echo(value: {annotation}): return value\n"
    with application(tmp_path / "bundle", source) as adapter:
        response = TestClient(adapter.app).post(
            "/capabilities/echo", json={"value": value}
        )
        assert response.status_code == 200, response.text
        assert response.json() == expected
        parsed = adapter.validate(
            value, adapter.PLAN["endpoints"][0]["parameters"][0]["type"]
        )
        if annotation.startswith("tuple"):
            assert isinstance(parsed, tuple)
        if annotation.startswith("set"):
            assert isinstance(parsed, set)


@pytest.mark.parametrize(
    ("annotation", "value"),
    [
        ("int", True),
        ("int", 1.5),
        ("int", "1"),
        ("str", 1),
        ("bool", 1),
        ("float", True),
        ("None", 0),
        ("list[int]", ["x"]),
        ("list[int]", {}),
        ("dict[str, int]", {"x": "1"}),
        ("dict[str, int]", []),
        ("tuple[int, str]", [1]),
        ("tuple[int, str]", [1, 2]),
        ("set[int]", [1, 1]),
        ("set", [[1]]),
        ("int | str", []),
        ("Optional[int]", "x"),
        ("Literal[1]", True),
        ("Literal[True]", 1),
        ("Literal['x']", "y"),
    ],
)
def test_invalid_input_is_422(tmp_path, annotation, value):
    with application(
        tmp_path / "bundle",
        f"from __future__ import annotations\ndef f(x: {annotation}): return x",
    ) as adapter:
        response = TestClient(adapter.app).post("/capabilities/f", json={"x": value})
        assert response.status_code == 422


def test_defaults_absence_is_distinct_from_null_and_mutable_default_is_not_copied(
    tmp_path,
):
    source = """def f(x: int = None, *, y: int | None = None):
    return [x, y]
def append(x: list = []):
    x.append(1)
    return x
"""
    with application(tmp_path / "bundle", source) as adapter:
        client = TestClient(adapter.app)
        assert client.post("/capabilities/f", json={}).json() == [None, None]
        assert client.post("/capabilities/f", json={"x": None}).status_code == 422
        assert client.post("/capabilities/f", json={"y": None}).status_code == 200
        assert client.post("/capabilities/append", json={}).json() == [1]
        assert client.post("/capabilities/append", json={}).json() == [1, 1]
        schema = client.get("/openapi.json").json()["paths"]["/capabilities/f"]["post"][
            "requestBody"
        ]["content"]["application/json"]["schema"]
        assert schema["required"] == []
        assert schema["properties"]["x"] == {"type": "integer"}
        assert "default" not in schema["properties"]["x"]


def test_sync_async_parameter_kinds_and_infrastructure_routes(tmp_path):
    source = """def health(a: int, /, b: int = 2, *, c: int = 3) -> int:
    return a + b + c
async def double(x: int) -> int:
    return x * 2
"""
    with application(
        tmp_path / "bundle", source, module_name="rest_project.pricing"
    ) as adapter:
        client = TestClient(adapter.app)
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/capabilities/health", json={"a": 1}).json() == 6
        assert (
            client.post("/capabilities/health", json={"a": 1, "b": 5, "c": 7}).json()
            == 13
        )
        assert client.post("/capabilities/double", json={"x": 3}).json() == 6
        assert client.get("/docs").status_code == 200
        assert client.get("/capabilities/health").status_code == 405
        schema = client.get("/openapi.json").json()
        assert (
            schema["paths"]["/capabilities/health"]["post"]["x-apizr-capability-id"]
            == "python:rest_project.pricing:health"
        )


@pytest.mark.parametrize("payload", [{"x": 1, "extra": 2}, {}, [1], None])
def test_extra_missing_and_non_object_body(tmp_path, payload):
    with application(tmp_path / "bundle", "def f(x: int): return x") as adapter:
        assert (
            TestClient(adapter.app).post("/capabilities/f", json=payload).status_code
            == 422
        )


def test_exception_boundary_and_return_documentation_without_enforcement(tmp_path):
    source = """def boom(): raise ValueError("secret implementation detail")
def intentional(): raise IntentionalError(status_code=409, detail="conflict")
def documented() -> int: return "not an integer"
def unknown() -> Missing: return {"ok": True}
"""
    # Future annotations keep unknown return declarations unevaluated at runtime.
    source = "from __future__ import annotations\n" + source
    with application(tmp_path / "bundle", source) as adapter:
        adapter.sys.modules["rest_sample"].IntentionalError = HTTPException
        client = TestClient(adapter.app)
        response = client.post("/capabilities/boom", json={})
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}
        assert "secret" not in response.text
        assert client.post("/capabilities/intentional", json={}).status_code == 409
        assert (
            client.post("/capabilities/documented", json={}).json() == "not an integer"
        )
        assert client.post("/capabilities/unknown", json={}).json() == {"ok": True}
        paths = client.get("/openapi.json").json()["paths"]
        assert paths["/capabilities/documented"]["post"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"] == {"type": "integer"}
        assert (
            paths["/capabilities/unknown"]["post"]["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
            == {}
        )


def test_positional_default_gaps_are_explicitly_rejected_and_documented(tmp_path):
    from jsonschema import Draft202012Validator

    source = "def f(a: int = 1, b: int = 2, /, *, c: int = 3): return [a, b, c]"
    with application(tmp_path / "bundle", source) as adapter:
        client = TestClient(adapter.app)
        schema = client.get("/openapi.json").json()["paths"]["/capabilities/f"]["post"][
            "requestBody"
        ]["content"]["application/json"]["schema"]
        assert schema["dependentRequired"] == {"b": ["a"]}
        for payload, expected in [
            ({}, [1, 2, 3]),
            ({"a": 4}, [4, 2, 3]),
            ({"a": 4, "b": 5}, [4, 5, 3]),
            ({"c": 6}, [1, 2, 6]),
        ]:
            assert Draft202012Validator(schema).is_valid(payload)
            assert client.post("/capabilities/f", json=payload).json() == expected
        assert not Draft202012Validator(schema).is_valid({"b": 5})
        response = client.post("/capabilities/f", json={"b": 5})
        assert response.status_code == 422
        assert "preceding positional-only field: a" in response.text


@pytest.mark.parametrize("annotation", ["Any", "float"])
def test_non_finite_request_numbers_are_rejected(tmp_path, annotation):
    source = f"from __future__ import annotations\ndef f(x: {annotation}): return x"
    with application(tmp_path / "bundle", source) as adapter:
        response = TestClient(adapter.app).post(
            "/capabilities/f",
            content='{"x": NaN}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


def test_json_serialization_failure_is_sanitized(tmp_path):
    with application(tmp_path / "bundle", "def f(): return float('nan')") as adapter:
        response = TestClient(adapter.app).post("/capabilities/f", json={})
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}

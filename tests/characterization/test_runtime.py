from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from .support import generate, runtime


@pytest.mark.parametrize(
    "source",
    [
        'def calculate(x: int): return x + 1\ndef calculate(x: str): return "last:" + x\n',
        "def calculate(x: int = 1): return x\ndef calculate(y: str): return y\n",
        "from typing import overload\n@overload\ndef choose(x: int) -> int: ...\n@overload\ndef choose(x: str) -> str: ...\ndef choose(x): return x\n",
        "if True:\n def choose(x): return x\nelse:\n def choose(y): return y\n",
    ],
)
def test_ambiguous_definitions_refused_before_generation_or_import(tmp_path, source):
    with pytest.raises(ValueError, match="Ambiguous function definitions"):
        generate(tmp_path, source)
    assert not list((tmp_path / "output").iterdir())


def test_false_branch_callable_is_discovered_but_unavailable_at_runtime(tmp_path):
    output = generate(tmp_path, "if False:\n    def absent(value: int): return value\n")
    with pytest.raises(AttributeError, match="absent"), runtime(output):
        pass


def test_generators_closures_and_return_annotations_are_not_response_schemas(tmp_path):
    output = generate(
        tmp_path,
        'def stream():\n    yield 1\n    yield 2\nasync def astream():\n    yield 1\ndef closure():\n    def inner(): return 1\n    return inner\ndef wrong() -> int:\n    return "not an integer"\n',
    )
    with runtime(output) as client:
        assert client.post("/stream").json() == [1, 2]
        assert client.post("/astream").json() == {"detail": "Function execution failed"}
        assert client.post("/closure").json() == {}
        assert client.post("/wrong").json() == "not an integer"
        assert (
            client.get("/openapi.json").json()["paths"]["/wrong"]["post"]["responses"][
                "200"
            ]["content"]["application/json"]["schema"]
            == {}
        )


def test_health_name_is_split_by_http_method_and_zero_args_ignore_body(tmp_path):
    output = generate(tmp_path, 'def health(): return "user health"\n')
    with runtime(output) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/health").json() == "user health"
        assert client.post("/health", json={"unexpected": 1}).status_code == 200
        assert set(client.get("/openapi.json").json()["paths"]["/health"]) == {"post"}


def test_reserved_parameter_names_nested_validation_and_exception_boundary(tmp_path):
    output = generate(
        tmp_path,
        """from fastapi import HTTPException
from pydantic import BaseModel
class Item(BaseModel):
    count: int
def names(_private: int, model_config: int, model_dump: int, field_1: int, __root__: int):
    return _private + model_config + model_dump + field_1 + __root__
def nested(items: list[Item]):
    return sum(item.count for item in items)
def fail():
    raise RuntimeError("private database password")
def expected():
    raise HTTPException(409, "public conflict")
""",
    )
    with runtime(output) as client:
        assert (
            client.post(
                "/names",
                json={
                    "_private": 1,
                    "model_config": 2,
                    "model_dump": 3,
                    "field_1": 4,
                    "__root__": 5,
                },
            ).json()
            == 15
        )
        assert (
            client.post("/nested", json={"items": [{"count": 1}] * 1000}).json() == 1000
        )
        for body in [
            {},
            {"items": [{}]},
            {"items": [{"count": []}]},
            {"items": [], "unexpected": 1},
        ]:
            assert client.post("/nested", json=body).status_code == 422
        assert client.post("/fail").json() == {"detail": "Function execution failed"}
        assert client.post("/expected").json() == {"detail": "public conflict"}


@settings(max_examples=20, deadline=None, print_blob=True)
@given(
    value=st.integers(-1000, 1000),
    asynchronous=st.booleans(),
    kind=st.sampled_from(["ordinary", "positional", "keyword", "default"]),
)
def test_property_runtime_signature_and_schema_agree(value, asynchronous, kind):
    arguments = {
        "ordinary": "value: int",
        "positional": "value: int, /",
        "keyword": "*, value: int",
        "default": "value: int = 7",
    }[kind]
    source = (
        f"{'async ' if asynchronous else ''}def echo({arguments}):\n    return value\n"
    )
    with TemporaryDirectory() as directory:
        output = generate(Path(directory), source, skip_docker=True, skip_pipreqs=True)
        with runtime(output) as client:
            assert client.post("/echo", json={"value": value}).json() == value
            assert client.post("/echo", json={"value": []}).status_code == 422
            assert (
                client.post("/echo", json={"value": value, "extra": True}).status_code
                == 422
            )
            assert client.post("/echo", json={}).status_code == (
                200 if kind == "default" else 422
            )
            schema = client.get("/openapi.json").json()["components"]["schemas"][
                "echo_Arguments"
            ]
            assert set(schema["properties"]) == {"value"}
            assert schema["additionalProperties"] is False
            assert schema.get("required", []) == (
                [] if kind == "default" else ["value"]
            )


def test_internal_pydantic_field_names_are_not_extra_public_parameters(tmp_path):
    output = generate(tmp_path, "def echo(value: int): return value\n")
    with runtime(output) as client:
        assert client.post("/echo", json={"field_1": 7}).status_code == 422


def test_none_default_is_not_the_same_as_optional_annotation(tmp_path):
    output = generate(
        tmp_path, "def optional_by_default(value: int = None): return value\n"
    )
    with runtime(output) as client:
        assert client.post("/optional_by_default").json() is None
        assert (
            client.post("/optional_by_default", json={"value": None}).status_code == 422
        )

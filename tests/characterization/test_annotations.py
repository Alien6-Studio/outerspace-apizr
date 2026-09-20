import json

import pytest
from pydantic.errors import PydanticSchemaGenerationError

from .support import analyze, corpus, generate, runtime

PREAMBLE = """import typing
from typing import Annotated, Callable, Literal, Mapping, Optional, Sequence, Union
from dataclasses import dataclass
from enum import Enum
from pydantic import BaseModel, Field
"""


@pytest.mark.parametrize("future", [False, True], ids=["eager", "future-annotations"])
@pytest.mark.parametrize("case", corpus("annotations.json"), ids=lambda c: c["id"])
def test_static_annotation_and_runtime_validation_are_separate(tmp_path, case, future):
    source = (
        ("from __future__ import annotations\n" if future else "")
        + PREAMBLE
        + case.get("preamble", "")
        + f"\ndef accept(value: {case['expression']}) -> {case['expression']}:\n    return value\n"
    )
    metadata = json.loads(analyze(source))["functions"][0]
    assert metadata["args"][0]["annotation"]["type"] == case["metadata_type"]
    assert metadata["returns"] == metadata["args"][0]["annotation"]
    output = generate(tmp_path, source, skip_docker=True, skip_pipreqs=True)
    behavior = case.get("runtime", "validated")
    if behavior in {"import_error", "unresolved_reference"}:
        error = (
            PydanticSchemaGenerationError if behavior == "import_error" else NameError
        )
        with pytest.raises(error), runtime(output):
            pass
        return
    with runtime(output) as client:
        if behavior == "dangling_schema_reference":
            schema = client.get("/openapi.json").json()
            reference = schema["paths"]["/accept"]["post"]["requestBody"]["content"][
                "application/json"
            ]["schema"]["$ref"]
            assert reference.rsplit("/", 1)[-1] not in schema["components"]["schemas"]
            assert (
                client.post("/accept", json={"value": case["invalid"]}).status_code
                == 422
            )
        else:
            schema = client.get("/openapi.json")
            assert schema.status_code == 200, schema.text
            assert "/accept" in schema.json()["paths"]
            assert (
                client.post("/accept", json={"value": case["valid"]}).status_code == 200
            )
            assert (
                client.post("/accept", json={"value": case["invalid"]}).status_code
                == 422
            )
            assert client.post("/accept", json={}).status_code == 422


def test_metadata_is_lossy_even_when_runtime_is_precise():
    def parameter(expression):
        return json.loads(analyze(f"def f(value: {expression}): pass"))["functions"][0][
            "args"
        ][0]["annotation"]

    assert parameter('Literal["a"]') == parameter('Literal["b"]')
    assert parameter('"User"') == parameter('"Other"') == {"type": "str", "of": []}
    assert parameter("list[int] | list[str]")["of"] == ["list", "list"]
    assert parameter("tuple[int, str]") != parameter("typing.Tuple[int, str]")

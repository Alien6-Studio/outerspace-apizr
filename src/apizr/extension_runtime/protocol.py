"""One UTF-8 JSON request/response per process; this protocol is not MCP."""

import json
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, JsonValue, TypeAdapter

from apizr.capabilities.types import ValueModel
from apizr.execution.protocol import finite_json

from .errors import PluginFailed, ProtocolInvalid

PROTOCOL = "apizr.extension/v1"
Identifier = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
Operation = Annotated[str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$")]


class Message(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    protocol: Literal["apizr.extension/v1"]
    request_id: Identifier
    operation: Operation


class Request(Message):
    arguments: dict[str, JsonValue]


class Response(Message):
    status: Literal["ok"]
    result: JsonValue


class RemoteError(ValueModel):
    code: Annotated[str, Field(min_length=1, max_length=128)]
    message: Annotated[str, Field(max_length=1024)]


class FailureResponse(Message):
    status: Literal["error"]
    error: RemoteError


RESPONSE: TypeAdapter[Response | FailureResponse] = TypeAdapter(
    Annotated[Response | FailureResponse, Field(discriminator="status")]
)


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def validate_response(raw: bytes, request: Request) -> Response:
    """Require a single finite JSON response bound to both ID and operation."""
    try:
        document = finite_json(
            json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        )
        response = RESPONSE.validate_python(document, strict=True)
        if (
            response.request_id != request.request_id
            or response.operation != request.operation
        ):
            raise ValueError("Mismatched response")
    except (ValueError, RecursionError):
        raise ProtocolInvalid() from None
    if isinstance(response, FailureResponse):
        # Even structured plugin diagnostics may contain secrets. Never include
        # remote messages, codes, raw stderr or request values in host errors.
        raise PluginFailed()
    return response

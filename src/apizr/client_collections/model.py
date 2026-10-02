"""Vendor-independent, portable client collection identities and limits."""

import json
import unicodedata
from pathlib import PurePosixPath
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, JsonValue, field_validator, model_validator

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.interfaces.serialization import json_bytes

Format = Literal["postman", "bruno", "insomnia"]
VERSIONS: dict[str, str] = {"postman": "3.0.0", "bruno": "1.0.0", "insomnia": "5.0/5.1"}
MAX_REQUESTS = 512
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_FILES = 2048
MANIFEST = "apizr-client-export.json"


class ClientError(ValueError):
    """Only fixed diagnostic codes cross the CLI boundary."""


def clean_text(value: str, limit: int = 256, *, multiline: bool = False) -> str:
    if (
        not value
        or len(value.encode("utf-8")) > limit
        or any(
            unicodedata.category(c).startswith("C") and not (multiline and c == "\n")
            for c in value
        )
    ):
        raise ValueError("invalid_text")
    return value


def validate_base_url(value: str) -> str:
    clean_text(value, 2048)
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or "?" in value
        or "#" in value
        or any(c.isspace() for c in value)
        or any(c in value for c in "\\{}")
        or parsed.port == 0
    ):
        raise ValueError("invalid_base_url")
    return value.rstrip("/")


def logical_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or len(value.encode()) > 512:
        raise ValueError("invalid_path")
    for part in path.parts:
        clean_text(part, 128)
        if (
            part in (".", "..")
            or part != part.strip()
            or part.endswith(".")
            or "\\" in part
            or ":" in part
        ):
            raise ValueError("invalid_path")
    if not path.parts:
        raise ValueError("invalid_path")
    return value


class StrictValue(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ClientSource(StrictValue):
    schema_version: Literal["apizr.repository-rest/v1", "apizr.rest/v1"]
    manifest_digest: Digest
    openapi_digest: Digest
    repository_interface_digest: Digest | None = None
    exposure_plan_digest: Digest | None = None
    ir_digest: Digest | None = None
    readiness_digest: Digest | None = None

    @model_validator(mode="after")
    def identities(self) -> Self:
        repository = self.schema_version == "apizr.repository-rest/v1"
        if any(
            (item is not None) != repository
            for item in (self.repository_interface_digest, self.exposure_plan_digest)
        ) or any(
            (item is not None) == repository
            for item in (self.ir_digest, self.readiness_digest)
        ):
            raise ValueError("source_identity_invalid")
        return self


class ClientRequest(StrictValue):
    capability_id: str
    name: str
    description: str | None = None
    method: Literal["POST"] = "POST"
    route: str
    request_schema: dict[str, JsonValue]
    response_schema: dict[str, JsonValue] | None
    example: dict[str, JsonValue]

    _names = field_validator("capability_id", "name")(lambda value: clean_text(value))

    @field_validator("description")
    @classmethod
    def description_text(cls, value: str | None) -> str | None:
        return clean_text(value, 8192, multiline=True) if value else value

    @field_validator("route")
    @classmethod
    def route_path(cls, value: str) -> str:
        if not value.startswith("/capabilities/") or not all(
            p.isidentifier() for p in value[14:].split(".")
        ):
            raise ValueError("invalid_route")
        return clean_text(value, 1024)


class ClientCollection(StrictValue):
    schema_version: Literal["apizr.client-collection/v1"] = "apizr.client-collection/v1"
    source: ClientSource
    name: str = "Apizr REST API"
    base_url: str = "http://127.0.0.1:8000"
    requests: tuple[ClientRequest, ...] = Field(min_length=1, max_length=MAX_REQUESTS)

    _name = field_validator("name")(lambda value: clean_text(value))
    _url = field_validator("base_url")(validate_base_url)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({r.capability_id for r in self.requests}) != len(self.requests) or len(
            {r.route for r in self.requests}
        ) != len(self.requests):
            raise ValueError("duplicate_request")
        return self


def canonical_bytes(value: ValueModel) -> bytes:
    return json_bytes(value.model_dump(mode="json"))


def collection_digest(value: ClientCollection) -> Digest:
    return Digest.of_bytes(canonical_bytes(value))


class GeneratedFile(StrictValue):
    path: str
    digest: Digest
    capability_ids: tuple[str, ...] = ()
    _path = field_validator("path")(logical_path)


class ExportOptions(StrictValue):
    name: str
    base_url: str
    _name = field_validator("name")(lambda value: clean_text(value))
    _url = field_validator("base_url")(validate_base_url)


class ClientExportManifest(StrictValue):
    schema_version: Literal["apizr.client-export/v1"] = "apizr.client-export/v1"
    format: Format
    format_version: str
    renderer: Literal["apizr.client-renderer/v1"] = "apizr.client-renderer/v1"
    client_collection_digest: Digest
    source_manifest_digest: Digest
    options: ExportOptions
    files: tuple[GeneratedFile, ...] = Field(min_length=1, max_length=MAX_FILES)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        paths = [f.path.casefold() for f in self.files]
        if (
            self.format_version != VERSIONS[self.format]
            or len(set(paths)) != len(paths)
            or MANIFEST in paths
        ):
            raise ValueError("export_identity_invalid")
        return self


class ClientExportResult(StrictValue):
    schema_version: Literal["apizr.client-export-result/v1"] = (
        "apizr.client-export-result/v1"
    )
    state: Literal["exported", "synced"]
    format: Format
    client_collection_digest: Digest
    source_manifest_digest: Digest
    files: tuple[GeneratedFile, ...]


def unique_json(data: bytes) -> JsonValue:
    def pairs(items: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    def invalid_constant(_: str) -> JsonValue:
        raise ValueError("nonfinite_json")

    return json.loads(
        data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant
    )

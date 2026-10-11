"""Verify retained REST artifacts and interpret invocation semantics exactly once."""

from pathlib import Path

from pydantic import JsonValue

from apizr.capabilities.inspection import Inspection
from apizr.capabilities.model import CapabilityDocument, Digest
from apizr.generators.rest.model import Manifest
from apizr.generators.rest.planner import plan as retained_rest_plan
from apizr.generators.rest.schema import openapi
from apizr.interfaces.model import TypeSpec
from apizr.interfaces.schema import json_schema, request_schema
from apizr.interfaces.serialization import json_bytes
from apizr.readiness.model import ReadinessReport
from apizr.repository_interfaces.model import RepositoryInterface, RestManifest
from apizr.workspace.files import directory_fd, read_regular

from .model import (
    MAX_FILE,
    MAX_FILES,
    MAX_REQUESTS,
    MAX_TOTAL,
    ClientCollection,
    ClientError,
    ClientRequest,
    ClientSource,
    clean_text,
    logical_path,
    unique_json,
)
from .model import (
    validate_base_url as validate_url,
)


def example_value(spec: TypeSpec, *, depth: int = 0) -> JsonValue:
    """Minimal JSON value; optional parameters are omitted by the caller."""
    if depth > 32:
        raise ClientError("client_collection_too_large")
    if spec.kind in ("any", "null"):
        return None
    if spec.kind == "int":
        return 0
    if spec.kind == "float":
        return 0.0
    if spec.kind == "str":
        return ""
    if spec.kind == "bool":
        return False
    if spec.kind == "dict":
        return {}
    if spec.kind == "object":
        return {
            field.name: example_value(field.type, depth=depth + 1)
            for field in spec.fields
            if field.required
        }
    if spec.kind in ("list", "set") or (spec.kind == "tuple" and spec.variadic):
        return []
    if spec.kind == "tuple":
        return [example_value(item, depth=depth + 1) for item in spec.items]
    if spec.kind == "literal" and spec.values:
        return spec.values[0]
    if spec.kind == "union" and spec.items:
        return example_value(spec.items[0], depth=depth + 1)
    raise ClientError("rest_bundle_invalid")


def plan_client_collection(
    bundle: str | Path,
    *,
    name: str = "Apizr REST API",
    base_url: str = "http://127.0.0.1:8000",
) -> ClientCollection:
    try:
        clean_text(name)
    except (ValueError, UnicodeError):
        raise ClientError("client_name_invalid") from None
    try:
        base_url = validate_url(base_url)
    except (ValueError, UnicodeError):
        raise ClientError("client_base_url_invalid") from None
    try:
        return _plan(Path(bundle), name, base_url)
    except ClientError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, RecursionError):
        raise ClientError("rest_bundle_invalid") from None


def _plan(bundle: Path, name: str, base_url: str) -> ClientCollection:
    import os

    with directory_fd(bundle) as root:
        names = set(os.listdir(root))
    manifests = names & {"apizr-rest.json", "apizr-repository-rest.json"}
    if len(manifests) != 1:
        raise ClientError("rest_bundle_invalid")
    manifest_name = next(iter(manifests))
    raw = read_regular(bundle / manifest_name, MAX_FILE)
    document = unique_json(raw)
    repository = manifest_name == "apizr-repository-rest.json"
    cls = RestManifest if repository else Manifest
    manifest = cls.model_validate_json(json_bytes(document), strict=True)
    endpoints = (
        manifest.endpoints
        if isinstance(manifest, RestManifest)
        else manifest.capabilities
    )
    if not 0 < len(endpoints) <= MAX_REQUESTS or len(manifest.artifacts) > MAX_FILES:
        raise ClientError("client_collection_too_large")
    # Only declared artifacts are read. No imports, scanning or runtime execution.
    artifacts: dict[str, bytes] = {}
    required = {"app.py", "requirements.txt", "openapi.json"}
    required |= (
        {"repository-interface.json", "exposure-plan.json"}
        if repository
        else {"capability-ir.json", "readiness.json"}
    )
    if not required <= manifest.artifacts.keys():
        raise ClientError("rest_bundle_invalid")
    total = len(raw)
    for path, digest in manifest.artifacts.items():
        logical_path(path)
        data = read_regular(bundle / path, MAX_FILE)
        total += len(data)
        if total > MAX_TOTAL:
            raise ClientError("client_collection_too_large")
        if Digest.of_bytes(data) != digest:
            raise ClientError("rest_bundle_changed")
        artifacts[path] = data
    document = unique_json(artifacts["openapi.json"])
    expected = openapi(endpoints)
    if repository:
        expected["info"] = {
            "title": "Apizr Repository REST API",
            "version": "apizr.repository-rest/v1",
        }
    if document != expected:
        raise ClientError("rest_bundle_changed")
    source_fields: dict[str, object] = {}
    if isinstance(manifest, RestManifest):
        contract = RepositoryInterface.model_validate_json(
            json_bytes(unique_json(artifacts["repository-interface.json"])), strict=True
        )
        if (
            Digest.of_bytes(artifacts["repository-interface.json"])
            != manifest.repository_interface_digest
            or Digest.of_bytes(artifacts["exposure-plan.json"])
            != manifest.exposure_plan_digest
            or contract.exposure_plan_digest != manifest.exposure_plan_digest
            or contract.interface != "rest"
            or contract.sources != manifest.sources
            or contract.application != manifest.application
            or len(contract.capabilities) != len(endpoints)
        ):
            raise ClientError("rest_bundle_changed")
        for capability, endpoint in zip(contract.capabilities, endpoints, strict=True):
            if (
                endpoint.model_dump(exclude={"route", "method"})
                != capability.invocation.model_dump()
                or endpoint.route != "/capabilities/" + capability.public_name
            ):
                raise ClientError("rest_bundle_changed")
        source_fields = {
            "repository_interface_digest": manifest.repository_interface_digest,
            "exposure_plan_digest": manifest.exposure_plan_digest,
        }
    else:
        if (
            Digest.of_bytes(artifacts["capability-ir.json"]) != manifest.ir_digest
            or Digest.of_bytes(artifacts["readiness.json"]) != manifest.readiness_digest
            or Digest.of_bytes(artifacts[manifest.executable_path])
            != manifest.executable_digest
        ):
            raise ClientError("rest_bundle_changed")
        retained = Inspection(
            capability_ir=CapabilityDocument.model_validate_json(
                json_bytes(unique_json(artifacts["capability-ir.json"])), strict=True
            ),
            readiness=ReadinessReport.model_validate_json(
                json_bytes(unique_json(artifacts["readiness.json"])), strict=True
            ),
            ir_digest=manifest.ir_digest,
            readiness_digest=manifest.readiness_digest,
        )
        executable = artifacts[manifest.executable_path]
        # Reuse the retained-contract binding check. This performs no scanning,
        # readiness assessment, repository exposure planning, imports or effects.
        expected_plan = retained_rest_plan(
            retained,
            artifacts["notebook.ipynb"]
            if manifest.source.kind == "notebook"
            else executable,
            executable=executable,
            select=[e.capability_id for e in endpoints],
        )
        if (
            expected_plan.source != manifest.source
            or expected_plan.endpoints != endpoints
            or expected_plan.executable_path != manifest.executable_path
        ):
            raise ClientError("rest_bundle_changed")
        for endpoint in endpoints:
            if (
                endpoint.route != "/capabilities/" + endpoint.name
                or endpoint.capability_id
                != f"python:{manifest.source.module}:{endpoint.name}"
            ):
                raise ClientError("rest_bundle_changed")
        source_fields = {
            "ir_digest": manifest.ir_digest,
            "readiness_digest": manifest.readiness_digest,
        }
    source = ClientSource.model_validate(
        dict(
            schema_version=manifest.schema_version,
            manifest_digest=Digest.of_bytes(raw),
            openapi_digest=Digest.of_bytes(artifacts["openapi.json"]),
            **source_fields,
        )
    )
    requests = tuple(
        ClientRequest(
            capability_id=e.capability_id,
            name=e.route.removeprefix("/capabilities/"),
            description=e.description,
            route=e.route,
            method=e.method,
            request_schema=request_schema(e),
            response_schema=json_schema(e.returns),
            example={p.name: example_value(p.type) for p in e.parameters if p.required},
        )
        for e in endpoints
    )
    return ClientCollection(
        source=source, name=name, base_url=base_url, requests=requests
    )

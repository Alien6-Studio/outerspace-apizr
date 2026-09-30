"""Pure vendor mappings; invocation interpretation lives entirely in the IR."""

import hashlib
import re
import unicodedata

from pydantic import JsonValue

from apizr.capabilities.model import Digest
from apizr.interfaces.serialization import json_bytes

from .model import (
    MANIFEST,
    MAX_FILE,
    MAX_FILES,
    MAX_TOTAL,
    VERSIONS,
    ClientCollection,
    ClientError,
    ClientExportManifest,
    ExportOptions,
    Format,
    GeneratedFile,
    canonical_bytes,
    collection_digest,
    logical_path,
)

IR_FILE = "apizr-client-collection.json"


def entity_id(
    collection: ClientCollection, format: Format, role: str, capability: str = ""
) -> str:
    return hashlib.sha256(
        json_bytes([format, collection_digest(collection).value, capability, role])
    ).hexdigest()[:32]


def request_names(collection: ClientCollection) -> tuple[str, ...]:
    names = []
    for request in collection.requests:
        text = (
            unicodedata.normalize("NFKD", request.name)
            .encode("ascii", "ignore")
            .decode()
        )
        stem = (
            re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-_").lower()[:64] or "request"
        )
        # Always namespace filenames by capability identity: stable even when a
        # later capability introduces a case/Unicode/truncation collision.
        suffix = hashlib.sha256(request.capability_id.encode()).hexdigest()[:16]
        names.append("request-" + stem + "-" + suffix)
    if len(set(names)) != len(names):
        raise ClientError("client_path_collision")
    return tuple(names)


def yaml_bytes(value: dict[str, JsonValue]) -> bytes:
    try:
        import yaml
    except ImportError:
        raise ClientError("clients_extra_required") from None

    class Dumper(yaml.SafeDumper):
        def ignore_aliases(self, data: object) -> bool:
            return True

    return yaml.dump(
        value,
        Dumper=Dumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        line_break="\n",
        width=10000,
    ).encode("utf-8")


def render_client_collection(
    collection: ClientCollection, *, format: Format
) -> dict[str, bytes]:
    if format not in VERSIONS:
        raise ClientError("client_format_unsupported")
    try:
        # Revalidate a detached snapshot, including caller-modified nested JSON.
        collection = ClientCollection.model_validate_json(
            canonical_bytes(collection), strict=True
        )
        return _render(collection, format)
    except ClientError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise ClientError("client_export_invalid") from None


def _render(collection: ClientCollection, format: Format) -> dict[str, bytes]:
    files: dict[str, bytes] = {IR_FILE: canonical_bytes(collection)}
    owners: dict[str, tuple[str, ...]] = {
        IR_FILE: tuple(r.capability_id for r in collection.requests)
    }

    def add(path: str, data: dict[str, JsonValue], ids: tuple[str, ...] = ()) -> None:
        files[path] = yaml_bytes(data)
        owners[path] = ids

    if format == "postman":
        add(
            ".resources/definition.yaml",
            {
                "$kind": "collection",
                "name": collection.name,
                "variables": {"base_url": collection.base_url},
            },
        )
    elif format == "bruno":
        add(
            "opencollection.yml",
            {
                "opencollection": "1.0.0",
                "info": {"name": collection.name},
                "request": {
                    "variables": [{"name": "base_url", "value": collection.base_url}]
                },
                "bundled": False,
            },
        )
    insomnia_requests: list[JsonValue] = []
    for index, (request, filename) in enumerate(
        zip(collection.requests, request_names(collection), strict=True), 1
    ):
        body = json_bytes(request.example).decode().rstrip("\n")
        description = (
            (request.description + "\n\n" if request.description else "")
            + "Apizr capability: "
            + request.capability_id
        )
        if format == "postman":
            add(
                filename + ".request.yaml",
                {
                    "$kind": "http-request",
                    "name": request.name,
                    "description": description,
                    "url": "{{base_url}}" + request.route,
                    "method": request.method,
                    "headers": {"Content-Type": "application/json"},
                    "body": {"type": "json", "content": body},
                    "order": index * 1000,
                },
                (request.capability_id,),
            )
        elif format == "bruno":
            add(
                filename + ".yml",
                {
                    "info": {
                        "name": request.name,
                        "type": "http",
                        "seq": index,
                        "description": description,
                    },
                    "http": {
                        "method": request.method,
                        "url": "{{base_url}}" + request.route,
                        "headers": [
                            {"name": "Content-Type", "value": "application/json"}
                        ],
                        "body": {"type": "json", "data": body},
                    },
                },
                (request.capability_id,),
            )
        else:
            insomnia_requests.append(
                {
                    "name": request.name,
                    "url": "{{ _.base_url }}" + request.route,
                    "method": request.method,
                    "meta": {
                        "id": "req_"
                        + entity_id(
                            collection, format, "request", request.capability_id
                        ),
                        "sortKey": index,
                        "description": description,
                    },
                    "headers": [{"name": "Content-Type", "value": "application/json"}],
                    "body": {"mimeType": "application/json", "text": body},
                    "settings": {"cookies": {"send": False, "store": False}},
                }
            )
    if format == "insomnia":
        add(
            "collection.yaml",
            {
                "type": "collection.insomnia.rest/5.0",
                "schema_version": "5.1",
                "name": collection.name,
                "meta": {"id": "wrk_" + entity_id(collection, format, "collection")},
                "collection": insomnia_requests,
                "environments": {
                    "name": "Base Environment",
                    "meta": {
                        "id": "env_" + entity_id(collection, format, "environment")
                    },
                    "data": {"base_url": collection.base_url},
                },
            },
            tuple(r.capability_id for r in collection.requests),
        )
    manifest = ClientExportManifest(
        format=format,
        format_version=VERSIONS[format],
        client_collection_digest=collection_digest(collection),
        source_manifest_digest=collection.source.manifest_digest,
        options=ExportOptions(name=collection.name, base_url=collection.base_url),
        files=tuple(
            GeneratedFile(
                path=path, digest=Digest.of_bytes(content), capability_ids=owners[path]
            )
            for path, content in sorted(files.items())
        ),
    )
    files[MANIFEST] = canonical_bytes(manifest)
    if (
        len(files) > MAX_FILES
        or sum(map(len, files.values())) > MAX_TOTAL
        or any(len(data) > MAX_FILE for data in files.values())
    ):
        raise ClientError("client_collection_too_large")
    for path in files:
        logical_path(path)
    return dict(sorted(files.items()))

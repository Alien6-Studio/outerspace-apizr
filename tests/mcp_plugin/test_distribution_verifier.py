"""External distribution failures remain distinct and never become offline CI I/O."""

import gzip
import hashlib
import io
import json
import sqlite3
import urllib.error
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import verify_mcp_distribution as verifier
from mcp_distribution import http, providers, snapshot
from mcp_distribution.metadata import (
    NAME,
    PACKAGES,
    REPOSITORY,
    REPOSITORY_URL,
    candidate_artifacts,
    validate_metadata,
)

SHA = "a" * 40


@pytest.fixture
def candidate():
    return {
        "schema": "apizr.release-candidate/v1",
        "repository": REPOSITORY,
        "version": "0.4.6",
        "commit": SHA,
        "artifacts": [
            {
                "file": name.replace("-", "_") + "-0.4.6" + suffix,
                "sha256": "b" * 64,
                "bytes": 1,
            }
            for name in PACKAGES
            for suffix in ("-py3-none-any.whl", ".tar.gz")
        ],
    }


@pytest.fixture
def tool_surface():
    return {
        "server": {"name": "apizr", "version": "0.4.6"},
        "tools": [
            {
                "name": "apizr_analyze",
                "title": "Analyze Python Project",
                "description": "Current qualified tool description",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "outputSchema": {"type": "object"},
            }
        ],
    }


@pytest.mark.parametrize(
    "fault", [None, "name", "version", "digest", "extra", "yanked", "marker"]
)
def test_pypi_checks_exact_artifacts_and_marker(candidate, fault):
    name = PACKAGES[1]
    hashes = candidate_artifacts(candidate, "0.4.6", SHA)[name]
    payload = {
        "info": {
            "name": name,
            "version": "0.4.6",
            "description": f"<!-- mcp-name: {NAME} -->",
        },
        "urls": [
            {"filename": n, "digests": {"sha256": h}, "yanked": False}
            for n, h in hashes.items()
        ],
    }
    if fault == "name":
        payload["info"]["name"] = "unrelated"
    elif fault == "version":
        payload["info"]["version"] = "0.4.4"
    elif fault == "digest":
        payload["urls"][0]["digests"]["sha256"] = "c" * 64
    elif fault == "extra":
        payload["urls"].append(
            {"filename": "unexpected.whl", "digests": {"sha256": "b" * 64}}
        )
    elif fault == "yanked":
        payload["urls"][0]["yanked"] = True
    elif fault == "marker":
        payload["info"]["description"] = "Wrong namespace"
    result = providers.pypi(payload, name, "0.4.6", hashes)
    assert result["status"] == (
        "verified" if fault is None else "stale" if fault == "version" else "mismatch"
    )


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "version",
        "namespace",
        "package",
        "config",
        "title",
        "repository",
        "inactive",
        "remote",
    ],
)
def test_official_registry_is_authoritative_for_exact_descriptor(fault):
    descriptor = validate_metadata()
    payload = {
        "server": deepcopy(descriptor),
        "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active"}},
    }
    server = payload["server"]
    if fault == "version":
        server["version"] = "0.4.4"
    elif fault == "namespace":
        server["name"] = "other/name"
    elif fault == "package":
        server["packages"][0]["identifier"] = "other-package"
    elif fault == "config":
        server["packages"][0]["packageArguments"][2]["isRequired"] = False
    elif fault == "title":
        server["title"] = "Wrong"
    elif fault == "repository":
        server["repository"]["url"] = "https://example.org/fork"
    elif fault == "inactive":
        payload["_meta"]["io.modelcontextprotocol.registry/official"]["status"] = (
            "deleted"
        )
    elif fault == "remote":
        server["remotes"] = [
            {"type": "streamable-http", "url": "https://example.org/mcp"}
        ]
    result = providers.official_registry(payload, descriptor)
    assert result["status"] == (
        "verified" if fault is None else "stale" if fault == "version" else "mismatch"
    )


def test_glama_cannot_pass_when_its_api_hides_required_evidence(tool_surface):
    tool = {
        k: v
        for k, v in tool_surface["tools"][0].items()
        if k in {"name", "description", "inputSchema"}
    }
    payload = {
        "namespace": "Alien6-Studio",
        "slug": "outerspace-apizr",
        "repository": {"url": REPOSITORY_URL},
        "url": "https://glama.ai/mcp/servers/Alien6-Studio/outerspace-apizr",
        "tools": [tool],
    }
    result = providers.glama(payload, tool_surface)
    assert (
        result["status"] == "not_checked" and result["verification"] == "not_verified"
    )
    assert "outputSchema" in result["unexposed_fields"]
    assert result["attribution"]["url"] == payload["url"]
    tool["outputSchema"] = tool_surface["tools"][0]["outputSchema"]
    assert providers.glama(payload, tool_surface)["status"] == "verified"
    tool["title"] = "Unexpected title if a later API exposes it"
    assert providers.glama(payload, tool_surface)["status"] == "stale"
    tool.pop("title")
    tool["description"] = "Old 0.4.4 metadata"
    assert providers.glama(payload, tool_surface)["status"] == "stale"
    payload["repository"]["url"] = "https://example.org/other"
    assert providers.glama(payload, tool_surface)["status"] == "mismatch"


@pytest.mark.parametrize(
    "fault", [None, "required", "default", "type", "remote", "tools", "bundle"]
)
def test_smithery_requires_actual_stdio_configuration_and_bundle(tool_surface, fault):
    manifest = {
        "user_config": {k: {} for k in ("project", "operator_policy", "plugins_dir")}
    }
    schema = {
        "type": "object",
        "required": list(manifest["user_config"]),
        "properties": {
            k: {"type": "string", "description": "Explicit user-selected value"}
            for k in manifest["user_config"]
        },
    }
    payload = {
        "remote": False,
        "connections": [{"type": "stdio", "configSchema": schema}],
        "tools": deepcopy(tool_surface["tools"]),
    }
    if fault == "required":
        schema["required"].pop()
    elif fault == "default":
        schema["properties"]["project"]["default"] = "."
    elif fault == "type":
        schema["properties"]["project"]["type"] = "boolean"
    elif fault == "remote":
        payload["remote"] = True
    elif fault == "tools":
        payload["tools"][0]["description"] = "old"
    result = providers.smithery(
        payload,
        tool_surface,
        manifest,
        None if fault == "bundle" else b"compared by caller",
    )
    assert result["status"] == {
        None: "verified",
        "tools": "stale",
        "bundle": "not_checked",
    }.get(fault, "mismatch")


@pytest.mark.parametrize(
    "code,state",
    [
        (401, "authentication_required"),
        (403, "authentication_required"),
        (404, "missing"),
        (429, "temporarily_unavailable"),
        (500, "temporarily_unavailable"),
        (302, "temporarily_unavailable"),
    ],
)
def test_http_errors_never_leak_keys_or_collapse_into_missing(monkeypatch, code, state):
    secret = "PRIVATE_PROVIDER_TOKEN"

    def open_request(request, **kwargs):
        assert request.get_method() == "GET"
        assert request.get_header("Authorization") == "Bearer " + secret
        raise urllib.error.HTTPError(
            request.full_url, code, secret, {}, io.BytesIO(secret.encode())
        )

    monkeypatch.setattr(
        http.urllib.request,
        "build_opener",
        lambda *_: SimpleNamespace(open=open_request),
    )
    body, result = http.fetch(
        "https://glama.ai/api/mcp/v1/servers/Alien6-Studio/outerspace-apizr",
        token=secret,
    )
    assert body is None and result["status"] == state
    assert secret not in json.dumps(result)


@pytest.mark.parametrize("payload", [b"not json", b"[]", b"\xff"])
def test_invalid_responses_are_unavailable_not_absent(monkeypatch, payload):
    monkeypatch.setattr(http, "fetch", lambda *a, **k: (payload, None))
    assert http.fetch_json("https://glama.ai")[1]["status"] == "temporarily_unavailable"


def test_get_client_bounds_and_authentication_destination(monkeypatch):
    called = []

    class Response(io.BytesIO):
        pass

    def open_request(request, **kwargs):
        called.append(request)
        return Response(b"x" * 6)

    monkeypatch.setattr(
        http.urllib.request,
        "build_opener",
        lambda *_: SimpleNamespace(open=open_request),
    )
    assert (
        http.fetch("https://pypi.org/pypi/example/json", limit=5)[1]["status"]
        == "temporarily_unavailable"
    )
    assert (
        http.fetch("https://untrusted.example/", token="PRIVATE")[1]["status"]
        == "mismatch"
    )
    assert http.fetch("http://glama.ai/")[1]["status"] == "mismatch"
    assert len(called) == 1
    assert (
        http.NoRedirect().redirect_request(
            None, None, 302, "", {}, "https://untrusted.example/"
        )
        is None
    )


def test_offline_is_default_even_when_provider_keys_exist(
    candidate, tool_surface, tmp_path, monkeypatch
):
    file, discovery = tmp_path / "candidate.json", tmp_path / "discovery.json"
    file.write_text(json.dumps(candidate))
    discovery.write_text(json.dumps(tool_surface))
    monkeypatch.setenv("GLAMA_API_KEY", "PRIVATE")
    monkeypatch.setenv("SMITHERY_API_KEY", "PRIVATE")
    monkeypatch.setattr(
        verifier,
        "fetch_json",
        lambda *a, **k: pytest.fail("Offline verification made a request"),
    )
    args = SimpleNamespace(
        candidate=file, discovery=discovery, source_sha=SHA, live=False
    )
    report = verifier.verify(args)
    assert not report["phase_b_complete"] and not report["publication_performed"]
    assert report["official_registry"]["status"] == "not_checked"
    assert "PRIVATE" not in json.dumps(report)


def test_missing_keys_report_not_verified_and_do_not_attempt_auth(
    candidate, tool_surface, tmp_path, monkeypatch
):
    file, discovery = tmp_path / "candidate.json", tmp_path / "discovery.json"
    file.write_text(json.dumps(candidate))
    discovery.write_text(json.dumps(tool_surface))
    monkeypatch.delenv("GLAMA_API_KEY", raising=False)
    monkeypatch.delenv("SMITHERY_API_KEY", raising=False)
    calls = []

    def checked(url, check, **kwargs):
        calls.append(url)
        return providers.outcome("missing", "Not released")

    monkeypatch.setattr(verifier, "checked", checked)
    args = SimpleNamespace(
        candidate=file,
        discovery=discovery,
        source_sha=SHA,
        live=True,
        include_mcpfinder=False,
    )
    report = verifier.verify(args)
    for name in ("glama", "smithery"):
        assert (
            report[name]["status"] == "authentication_required"
            and report[name]["verification"] == "not_verified"
        )
    assert len(calls) == 3 and not report["phase_b_complete"]


def test_local_directory_keys_are_not_consumed(
    candidate, tool_surface, tmp_path, monkeypatch
):
    file, discovery = tmp_path / "candidate.json", tmp_path / "discovery.json"
    file.write_text(json.dumps(candidate))
    discovery.write_text(json.dumps(tool_surface))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("GLAMA_API_KEY", "PRIVATE_LOCAL_KEY")
    monkeypatch.setenv("SMITHERY_API_KEY", "PRIVATE_LOCAL_KEY")
    calls = []

    def checked(url, check, **kwargs):
        calls.append((url, kwargs))
        return providers.outcome("missing", "Not released")

    monkeypatch.setattr(verifier, "checked", checked)
    report = verifier.verify(
        SimpleNamespace(
            candidate=file,
            discovery=discovery,
            source_sha=SHA,
            live=True,
            include_mcpfinder=False,
        )
    )
    assert len(calls) == 3 and all(not kwargs.get("token") for _, kwargs in calls)
    assert (
        report["glama"]["verification"]
        == report["smithery"]["verification"]
        == "not_verified"
    )
    assert "PRIVATE_LOCAL_KEY" not in json.dumps(report)


def test_actions_keys_are_scoped_and_never_retained(
    candidate, tool_surface, tmp_path, monkeypatch
):
    file, discovery = tmp_path / "candidate.json", tmp_path / "discovery.json"
    file.write_text(json.dumps(candidate))
    discovery.write_text(json.dumps(tool_surface))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GLAMA_API_KEY", "PRIVATE_GLAMA")
    monkeypatch.setenv("SMITHERY_API_KEY", "PRIVATE_SMITHERY")

    def checked(url, check, *, token=None):
        assert token == (
            "PRIVATE_GLAMA" if url.startswith("https://glama.ai/") else None
        )
        return providers.outcome("temporarily_unavailable", "Test provider unavailable")

    def smithery(name, token, discovery, bundle):
        assert name == "studio/apizr" and token == "PRIVATE_SMITHERY"
        return providers.outcome(
            "authentication_required", "Test provider refused access"
        )

    monkeypatch.setattr(verifier, "checked", checked)
    monkeypatch.setattr(verifier, "inspect_smithery", smithery)
    report = verifier.verify(
        SimpleNamespace(
            candidate=file,
            discovery=discovery,
            source_sha=SHA,
            live=True,
            include_mcpfinder=False,
            smithery_name="studio/apizr",
            smithery_bundle=None,
        )
    )
    assert "PRIVATE" not in json.dumps(report) and not report["phase_b_complete"]


def test_smithery_download_binds_exact_manifest_and_documented_route(
    tool_surface, tmp_path, monkeypatch
):
    from build_mcp_bundle import build
    from mcp_distribution.metadata import ROOT, read

    bundle = tmp_path / "expected.mcpb"
    build(bundle)
    manifest = read(ROOT / "plugins/mcp/distribution/manifest.json")
    payload = {
        "qualifiedName": "studio/apizr",
        "remote": False,
        "connections": [
            {
                "type": "stdio",
                "configSchema": {
                    "required": list(manifest["user_config"]),
                    "properties": {
                        k: {"type": "string", "description": v["description"]}
                        for k, v in manifest["user_config"].items()
                    },
                },
            }
        ],
        "tools": tool_surface["tools"],
    }
    monkeypatch.setattr(verifier, "fetch_json", lambda *a, **k: (payload, None))

    def fetch(url, *, token, limit):
        assert url == "https://api.smithery.ai/servers/studio%2Fapizr/download"
        assert token == "PRIVATE_SMITHERY"
        return bundle.read_bytes(), None

    monkeypatch.setattr(verifier, "fetch", fetch)
    assert (
        verifier.inspect_smithery(
            "studio/apizr", "PRIVATE_SMITHERY", tool_surface, bundle
        )["status"]
        == "verified"
    )
    bundle.write_bytes(b"different wrapper")
    assert (
        verifier.inspect_smithery(
            "studio/apizr", "PRIVATE_SMITHERY", tool_surface, bundle
        )["status"]
        == "mismatch"
    )


@pytest.mark.parametrize(
    "fault", ["bad_size", "compressed_corrupt", "truncated", "query_error"]
)
def test_mcpfinder_malformed_or_unavailable_evidence_cannot_pass(monkeypatch, fault):
    compressed = gzip.compress(b"not a database")
    if fault == "compressed_corrupt":
        compressed = b"not gzip"
    if fault == "truncated":
        compressed = compressed[:-2]
    manifest = {
        "sha256": hashlib.sha256(compressed).hexdigest(),
        "sizeBytes": "bad" if fault == "bad_size" else len(compressed),
        "rawSizeBytes": 14,
        "publishedAt": datetime.now(timezone.utc).isoformat(),
    }
    monkeypatch.setattr(snapshot, "fetch_json", lambda *a, **k: (manifest, None))
    monkeypatch.setattr(snapshot, "fetch", lambda *a, **k: (compressed, None))
    result = snapshot.live_snapshot("0.4.6")
    assert (
        result["status"] == "temporarily_unavailable"
        and result["verification"] == "not_verified"
    )


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "old_version",
        "single_source",
        "identity",
        "missing",
        "digest",
        "old_snapshot",
        "raw_size",
    ],
)
def test_mcpfinder_digest_bound_read_only_snapshot(tmp_path, fault):
    now = datetime.now(timezone.utc)
    path = tmp_path / "source.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE servers (repository_url TEXT, version TEXT, package_identifier TEXT, transport_type TEXT, status TEXT, sources TEXT)"
        )
        if fault != "missing":
            db.execute(
                "INSERT INTO servers VALUES (?, ?, ?, ?, ?, ?)",
                (
                    REPOSITORY_URL,
                    "0.4.4" if fault == "old_version" else "0.4.6",
                    "other" if fault == "identity" else PACKAGES[1],
                    "stdio",
                    "active",
                    json.dumps(
                        ["official"]
                        if fault == "single_source"
                        else ["official", "glama", "smithery"]
                    ),
                ),
            )
    raw = path.read_bytes()
    compressed = gzip.compress(raw)
    manifest = {
        "sha256": hashlib.sha256(compressed).hexdigest(),
        "sizeBytes": len(compressed),
        "rawSizeBytes": len(raw),
        "publishedAt": (
            now - timedelta(hours=19) if fault == "old_snapshot" else now
        ).isoformat(),
    }
    if fault == "digest":
        manifest["sha256"] = "f" * 64
    if fault == "raw_size":
        manifest["rawSizeBytes"] += 1
    result = snapshot.inspect_snapshot(manifest, compressed, "0.4.6", now=now)
    assert result["status"] == {
        None: "verified",
        "old_version": "stale",
        "single_source": "stale",
        "old_snapshot": "stale",
        "missing": "missing",
    }.get(fault, "mismatch")
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "fault", ["sha", "version", "repository", "missing", "duplicate", "digest", "path"]
)
def test_candidate_manifest_cannot_substitute_another_release(candidate, fault):
    if fault == "sha":
        candidate["commit"] = "c" * 40
    elif fault == "version":
        candidate["version"] = "0.4.4"
    elif fault == "repository":
        candidate["repository"] = "Other/fork"
    elif fault == "missing":
        candidate["artifacts"].pop()
    elif fault == "duplicate":
        candidate["artifacts"].append(candidate["artifacts"][0])
    elif fault == "digest":
        candidate["artifacts"][0]["sha256"] = "bad"
    elif fault == "path":
        candidate["artifacts"][0]["file"] = "../" + candidate["artifacts"][0]["file"]
    with pytest.raises(ValueError):
        candidate_artifacts(candidate, "0.4.6", SHA)

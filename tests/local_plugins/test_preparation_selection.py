"""Artifact selection needs target priority, admitted hashes and actual bytes."""

import hashlib
import importlib.util
import json
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from apizr.plugins.lock.models import Target
from apizr.plugins.preparation import selection
from apizr.plugins.preparation.models import AdmittedPin, Control, PreparationError
from apizr.plugins.preparation.selection import Candidate

SPEC = importlib.util.spec_from_file_location(
    "preparation_https_fixture",
    Path(__file__).resolve().parents[2] / "scripts/https_fixture.py",
)
assert SPEC and SPEC.loader
https = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(https)

TARGET = Target(
    implementation="cpython",
    python="3.14.0",
    platform="macosx-15.0-x86_64",
    machine="x86_64",
    abi="cpython-314-darwin",
)
HASH = "a" * 64
PIN = AdmittedPin(name="example", version="1.0", hashes=(HASH,))


def candidate(tag, digest=HASH):
    return Candidate(f"example-1.0-{tag}.whl", digest)


def test_explicit_interpreter_prefers_exact_abi_then_recent_stable_abi():
    native = candidate("cp314-cp314-macosx_14_0_x86_64")
    recent = candidate("cp311-abi3-macosx_11_0_x86_64")
    old = candidate("cp39-abi3-macosx_11_0_x86_64")
    universal = candidate("py3-none-any")
    assert selection.select(PIN, [universal, old, recent, native], TARGET) == native
    assert selection.select(PIN, [old, recent, universal], TARGET) == recent
    assert selection.select(PIN, [universal, recent, old], TARGET) == recent


def test_best_wheel_with_unadmitted_hash_does_not_fallback_to_weaker_match():
    native = candidate("cp314-cp314-macosx_14_0_x86_64", "b" * 64)
    with pytest.raises(PreparationError, match="wheel_hash_not_admitted"):
        selection.select(PIN, [candidate("py3-none-any"), native], TARGET)


def test_free_threaded_target_refuses_conventional_stable_abi():
    with pytest.raises(PreparationError, match="compatible_wheel_unavailable"):
        selection.select(
            PIN,
            [candidate("cp311-abi3-macosx_11_0_x86_64")],
            TARGET.model_copy(update={"abi": "cpython-314t-darwin"}),
        )


def evidence(wheels, **changes):
    package = {"name": "example", "version": "1.0", "wheels": wheels, **changes}

    # Fixed structure preserves arbitrary hostile values without a TOML dependency.
    def value(item):
        if isinstance(item, dict):
            return (
                "{"
                + ",".join(f"{key}={value(data)}" for key, data in item.items())
                + "}"
            )
        if isinstance(item, list):
            return "[" + ",".join(map(value, item)) + "]"
        return json.dumps(item)

    return (
        'lock-version="1.0"\ncreated-by="uv"\npackages=[' + value(package) + "]"
    ).encode()


def test_machine_evidence_accepts_https_and_explicit_local_snapshot(
    wheel_factory, tmp_path
):
    wheel, digest = wheel_factory(name="example", plugin=False)
    remote = {
        "url": "https://files.example.test/" + wheel.name,
        "hashes": {"sha256": digest},
    }
    local = {"url": wheel.as_uri(), "hashes": {}}
    path = {"path": str(wheel), "hashes": {"sha256": digest}}
    pin = AdmittedPin(name="example", version="1.0", hashes=(digest,))
    result = selection.resolver_candidates(
        evidence([remote, local, path]), (pin,), tmp_path
    )
    assert [item.sha256 for item in result["example"]] == [digest] * 3
    assert result["example"][1].path == wheel
    with pytest.raises(PreparationError, match="wheel_selection_ambiguous"):
        selection.select(pin, result["example"], TARGET)


@pytest.mark.parametrize(
    "wheel",
    [
        {
            "url": "http://files.test/example-1.0-py3-none-any.whl",
            "hashes": {"sha256": HASH},
        },
        {
            "url": "https://user:secret@files.test/example-1.0-py3-none-any.whl",
            "hashes": {"sha256": HASH},
        },
        {"url": "file://host/secret.whl", "hashes": {}},
        {"url": "file:///secret.whl?token=secret", "hashes": {}},
        {"path": "/outside/example-1.0-py3-none-any.whl", "hashes": {}},
        {
            "url": "https://files.test/other-1.0-py3-none-any.whl",
            "hashes": {"sha256": HASH},
        },
        {"url": "https://files.test/example-1.0-py3-none-any.whl", "hashes": []},
        {"url": "https://files.test/example-1.0-py3-none-any.whl", "hashes": {}},
        {"path": "anything", "url": "anything", "hashes": {}},
        {"hashes": {}},
    ],
)
def test_machine_evidence_refuses_untrusted_sources_and_identities(wheel, tmp_path):
    with pytest.raises(PreparationError, match="invalid_resolver_artifacts"):
        selection.resolver_candidates(evidence([wheel]), (PIN,), tmp_path)


def test_source_archives_and_unbounded_candidate_lists_are_refused(monkeypatch):
    with pytest.raises(PreparationError, match="compatible_wheel_unavailable"):
        selection.resolver_candidates(
            evidence([], sdist={"url": "https://files.test/evil.tar.gz"}), (PIN,), None
        )
    monkeypatch.setattr(selection, "MAX_CANDIDATES", 0)
    with pytest.raises(PreparationError, match="too_many_artifact_candidates"):
        selection.resolver_candidates(evidence([{}]), (PIN,), None)
    with pytest.raises(PreparationError, match="invalid_wheel_tags"):
        selection.select(PIN, [candidate("py3-none-any")], TARGET)


@pytest.mark.parametrize(
    "mode", ["valid", "altered", "http_error", "post_transfer_tamper"]
)
def test_real_download_checks_retained_bytes_and_admitted_hashes(
    wheel_factory, tmp_path, monkeypatch, mode
):
    wheel, digest = wheel_factory()
    body = wheel.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if mode == "http_error":
                self.send_error(403)
                return
            data = body + (b"changed" if mode == "altered" else b"")
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    cert, key = https.certificate(tmp_path)
    real_run = selection.run

    def transfer(arguments, *args, **kwargs):
        control_file = Path(arguments[-1])
        request = json.loads(control_file.read_bytes())
        request["ca_file"] = str(cert)
        control_file.write_text(json.dumps(request))
        result = real_run(arguments, *args, **kwargs)
        if mode == "post_transfer_tamper":
            Path(request["destination"]).write_bytes(
                body + b"changed-after-verification"
            )
        return result

    monkeypatch.setattr(selection, "run", transfer)
    pin = AdmittedPin(name="local-probe", version="1.0", hashes=(digest,))
    with https.https_server(cert, key, Handler) as url:
        candidates = {
            pin.name: [Candidate(wheel.name, digest, url=url + "/" + wheel.name)]
        }

        def retain():
            return selection.retain(
                (pin,),
                candidates,
                TARGET,
                pin.name,
                tmp_path / "house",
                tmp_path,
                Control(time.monotonic() + 10),
            )

        if mode == "valid":
            artifacts, manifest = retain()
            assert manifest.name == pin.name and artifacts[0].sha256 == digest
            assert (
                hashlib.sha256(
                    (tmp_path / "house" / wheel.name).read_bytes()
                ).hexdigest()
                == digest
            )
        else:
            with pytest.raises((PreparationError, ValueError)) as caught:
                retain()
            assert isinstance(caught.value, PreparationError)
            assert caught.value.diagnostic.reason == (
                "artifact_download_failed"
                if mode == "http_error"
                else "wheel_hash_not_admitted"
            )


def test_candidate_identity_and_local_digest_must_match_evidence(
    wheel_factory, tmp_path
):
    wheel, digest = wheel_factory(name="example", plugin=False)
    with pytest.raises(PreparationError, match="invalid_resolver_artifacts"):
        selection.resolver_candidates(evidence([], version="2.0"), (PIN,), None)
    with pytest.raises(PreparationError, match="invalid_resolver_artifacts"):
        selection.resolver_candidates(
            evidence([{"path": str(wheel), "hashes": {"sha256": "0" * 64}}]),
            (PIN,),
            tmp_path,
        )
    unknown, _ = wheel_factory(name="unrelated", plugin=False)
    assert list(selection.local_candidates(tmp_path, (PIN,))) == ["example"]
    unknown.rename(tmp_path / "invalid.whl")
    with pytest.raises(PreparationError, match="invalid_wheel_filename"):
        selection.local_candidates(tmp_path, (PIN,))


@pytest.mark.parametrize(
    "mode",
    [
        "missing_tags",
        "oversized_tags",
        "identity",
        "missing_plugin",
        "invalid_manifest",
        "total_bytes",
        "expanded_bytes",
    ],
)
def test_retained_wheels_need_complete_bounded_metadata(
    wheel_factory, tmp_path, monkeypatch, mode
):
    wheel, digest = wheel_factory(
        manifest_changes={"version": "2.0"} if mode == "invalid_manifest" else None
    )
    pin = AdmittedPin(name="local-probe", version="1.0", hashes=(digest,))
    name = pin.name
    reason = None
    if mode == "missing_tags":
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("irrelevant", b"content")
        with pytest.raises(PreparationError, match="invalid_wheel_tags"):
            selection._wheel_tags(buffer.getvalue(), wheel.name)
        return
    if mode == "oversized_tags":
        monkeypatch.setattr(selection, "MAX_METADATA_BYTES", 1)
        reason = "invalid_wheel_tags"
    elif mode == "identity":
        name = "wrong-name"
        pin = AdmittedPin(name=name, version="1.0", hashes=(digest,))
        reason = "dependency_lock_mismatch"
    elif mode == "missing_plugin":
        name = "missing-plugin"
        reason = "plugin_not_in_resolver_lock"
    elif mode == "invalid_manifest":
        reason = "inconsistent_metadata"
    elif mode == "total_bytes":
        monkeypatch.setattr(selection, "MAX_TOTAL_BYTES", 1)
        reason = "wheelhouse_too_large"
    elif mode == "expanded_bytes":
        monkeypatch.setattr(selection, "MAX_TOTAL_EXPANDED_BYTES", 1)
        reason = "wheelhouse_too_large"
    with pytest.raises(PreparationError, match=reason):
        selection.retain(
            (pin,),
            {pin.name: [Candidate(wheel.name, digest, path=wheel)]},
            TARGET,
            name,
            tmp_path / "retained",
            tmp_path,
            Control(time.monotonic() + 5),
        )


def test_real_index_with_only_sdist_refuses_without_running_source(
    wheel_factory, tmp_path, monkeypatch
):
    import io
    import sys
    import tarfile

    from apizr.plugins.preparation import resolver
    from apizr.plugins.preparation.operations import prepare_plugin

    wheel, digest = wheel_factory(metadata_extra="Requires-Dist: sdist-trap==1.0\n")
    marker = tmp_path / "SOURCE-BACKEND-MUST-NOT-RUN"
    archive = io.BytesIO()
    files = {
        "pyproject.toml": b'[build-system]\nrequires=[]\nbuild-backend="evil"\nbackend-path=["."]\n[project]\nname="sdist-trap"\nversion="1.0"\n',
        "PKG-INFO": b"Metadata-Version: 2.3\nName: sdist-trap\nVersion: 1.0\n",
        "evil.py": f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('source execution forbidden')\n".encode(),
    }
    with tarfile.open(fileobj=archive, mode="w:gz") as source:
        for name, raw in files.items():
            member = tarfile.TarInfo("sdist-trap-1.0/" + name)
            member.size = len(raw)
            source.addfile(member, io.BytesIO(raw))
    source_bytes = archive.getvalue()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    requested = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            requested.append(self.path)
            responses = {
                "/simple/local-probe/": f'<a href="/files/{wheel.name}#sha256={digest}">{wheel.name}</a>'.encode(),
                "/simple/sdist-trap/": f'<a href="/files/sdist-trap-1.0.tar.gz#sha256={source_hash}">sdist-trap-1.0.tar.gz</a>'.encode(),
                "/files/" + wheel.name: wheel.read_bytes(),
                "/files/sdist-trap-1.0.tar.gz": source_bytes,
            }
            body = responses.get(self.path)
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Content-Type",
                "text/html"
                if self.path.startswith("/simple/")
                else "application/octet-stream",
            )
            self.end_headers()
            if self.command == "GET":
                self.wfile.write(body)

    cert, key = https.certificate(tmp_path)
    # uv's Rust TLS stack correctly rejects a CA certificate used as a leaf.
    # Issue a separate localhost server certificate from the explicit test CA.
    import subprocess

    server_cert, server_key = tmp_path / "server.pem", tmp_path / "server-key.pem"
    request, config = tmp_path / "server.csr", tmp_path / "server.cnf"
    config.write_text(
        (tmp_path / "openssl.cnf").read_text().replace("CA:TRUE", "CA:FALSE")
    )
    for arguments in (
        [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-config",
            str(config),
            "-keyout",
            str(server_key),
            "-out",
            str(request),
        ],
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(request),
            "-CA",
            str(cert),
            "-CAkey",
            str(key),
            "-CAcreateserial",
            "-days",
            "1",
            "-extfile",
            str(config),
            "-extensions",
            "extensions",
            "-out",
            str(server_cert),
        ],
    ):
        subprocess.run(arguments, check=True, capture_output=True, timeout=20)
    real_run = resolver.run
    resolver_errors = []

    def trusted_fixture(arguments, *args, **kwargs):
        kwargs["environment"] = {
            **kwargs.get("environment", {}),
            "SSL_CERT_FILE": str(cert),
        }
        reply = real_run(arguments, *args, **kwargs)
        resolver_errors.append(reply.stderr.decode())
        return reply

    monkeypatch.setattr(resolver, "run", trusted_fixture)
    with https.https_server(server_cert, server_key, Handler) as url:
        result = prepare_plugin(
            "local-probe",
            "1.0",
            python=Path(sys.executable),
            platform="native",
            index_url=url + "/simple",
            output_dir=tmp_path / "prepared",
        )
    assert result.state == "refused", result
    assert result.diagnostics[0].reason == "compatible_wheel_unavailable", (
        result,
        resolver_errors,
        requested,
    )
    assert result.diagnostics[0].distribution == "sdist-trap"
    assert "/simple/sdist-trap/" in requested
    assert "/files/sdist-trap-1.0.tar.gz" not in requested
    assert not marker.exists() and not (tmp_path / "prepared").exists()
    assert not list(tmp_path.glob(".apizr-preparation-*"))

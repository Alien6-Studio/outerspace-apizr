import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest
from apizr_attest import delivery
from apizr_attest.model import AttestError, AttestRequest, VerifyRequest
from apizr_attest.process import run
from apizr_oci.model import BuildError
from apizr_oci.observe import Observation


def documents(tmp_path):
    raw = delivery.canonical(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {"digest": "sha256:" + "1" * 64},
            "layers": [],
        }
    )
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    reference = "registry.test:5443/services/rest@" + digest
    built = {
        "schema": "apizr.oci-build-result/v1",
        "tag": "local:test",
        "image_id": "sha256:" + "1" * 64,
        "inputs_sha256": "2" * 64,
        "platform": "linux/amd64",
        "published": False,
    }
    pushed = built | {
        "schema": "apizr.oci-push-result/v1",
        "destination": "registry.test:5443/services/rest:v1",
        "digest_reference": reference,
        "config_digest": built["image_id"],
        "manifest_digest": digest,
        "index_digest": None,
        "published": True,
    }
    del pushed["tag"]
    (tmp_path / "build.json").write_bytes(delivery.canonical(built))
    (tmp_path / "push.json").write_bytes(delivery.canonical(pushed))
    (tmp_path / "key").write_bytes(b"PRIVATE KEY test sentinel")
    (tmp_path / "trust").mkdir()
    request = AttestRequest.model_validate(
        {
            "schema": "apizr.attest-delivery/v1",
            "expected_reference": reference,
            "expected_signer": "3" * 64,
            "trust_store": str(tmp_path / "trust"),
            "tool": {
                "executable": shutil.which("true"),
                "version": "0.1.0",
                "sha256": "4" * 64,
            },
            "build_result": str(tmp_path / "build.json"),
            "push_result": str(tmp_path / "push.json"),
            "docker": {
                "executable": shutil.which("true"),
                "socket": str(tmp_path / "socket"),
            },
            "authentication": {"config_file": str(tmp_path / "auth")},
            "key_file": str(tmp_path / "key"),
            "key_id": "5" * 32,
            "tsa_url": "http://127.0.0.1:1234",
            "output_dir": str(tmp_path / "output"),
        }
    )
    return request, built, pushed, raw


def verdict():
    return {
        "verdict": "pass",
        "signed_by": "3" * 64,
        "warnings": [],
        "checks": [
            {"name": name, "status": "pass"} for name in sorted(delivery.CHECKS)
        ],
    }


@pytest.mark.parametrize(
    "fault",
    [
        "global",
        "signer",
        "warnings",
        "missing",
        "duplicate",
        "skipped",
        "null",
        "nonobject",
    ],
)
def test_strict_verdict(fault):
    report = verdict()
    if fault == "global":
        report["verdict"] = "fail"
    if fault == "signer":
        report["signed_by"] = "4" * 64
    if fault == "warnings":
        report["warnings"] = ["revoked"]
    if fault == "missing":
        report["checks"].pop()
    if fault == "duplicate":
        report["checks"][0] = report["checks"][1]
    if fault == "skipped":
        report["checks"][0]["status"] = "skipped"
    if fault == "null":
        report["checks"] = None
    if fault == "nonobject":
        report = []
    with pytest.raises(AttestError):
        delivery.validate_verdict(report, "3" * 64)


@pytest.fixture
def mocked(tmp_path, monkeypatch):
    request, built, pushed, raw = documents(tmp_path)
    monkeypatch.setattr(delivery, "tool", lambda *args: Path("/bin/true"))
    monkeypatch.setattr(
        delivery,
        "observe",
        lambda *a, **k: Observation(
            pushed["config_digest"], pushed["manifest_digest"], raw
        ),
    )

    def native(executable, args, work, deadline, limit):
        if args[0] == "run":
            assert (
                work / ".attest/keys" / ("5" * 32 + ".key")
            ).stat().st_mode & 0o777 == 0o600
            delivery.write(
                work / ".attest/receipts/one.yaml", b"native-receipt-placeholder"
            )
            return b""
        assert (
            "--offline" in args
            and "--recompute" in args
            and "--trust-receipt-timestamp" not in args
        )
        assert not list((work / ".attest/keys").glob("*.key"))
        return json.dumps(verdict()).encode()

    monkeypatch.setattr(delivery, "run", native)
    return request


def test_private_export_copy_binding_and_no_overwrite(mocked, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    result = delivery.execute_attest(mocked, work)
    assert result.receipt_published is False
    output = Path(mocked.output_dir)
    assert sorted(
        str(p.relative_to(output)) for p in output.rglob("*") if p.is_file()
    ) == sorted(delivery.FILES)
    assert not any(
        b"PRIVATE KEY" in p.read_bytes() for p in output.rglob("*") if p.is_file()
    )
    assert (tmp_path / "key").read_bytes() == b"PRIVATE KEY test sentinel"
    another = tmp_path / "verify"
    another.mkdir()
    verified = VerifyRequest.model_validate(
        {
            "schema": "apizr.verify-delivery/v1",
            **mocked.model_dump(
                include={"expected_reference", "expected_signer", "trust_store", "tool"}
            ),
            "proof_dir": str(output),
        }
    )
    assert delivery.execute_verify(verified, another) == result
    with pytest.raises(AttestError, match="proof_already_exists"):
        delivery.execute_attest(mocked, work)


@pytest.mark.parametrize(
    "fault", ["manifest", "build", "push", "pipeline", "reference", "binding"]
)
def test_tampered_binding_refused(mocked, tmp_path, fault):
    work = tmp_path / "work"
    work.mkdir()
    delivery.execute_attest(mocked, work)
    proof = Path(mocked.output_dir)
    reference = mocked.expected_reference
    if fault == "reference":
        reference = reference.replace("services/rest", "services/other")
    else:
        name = {
            "manifest": "delivery/oci-manifest.json",
            "build": "delivery/build.json",
            "push": "delivery/push.json",
            "pipeline": "attest.yaml",
            "binding": "delivery/manifest.json",
        }[fault]
        path = proof / name
        if fault in {"build", "push"}:
            doc = json.loads(path.read_bytes())
            doc["inputs_sha256"] = "9" * 64
            path.write_bytes(delivery.canonical(doc))
        else:
            path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises((AttestError, ValueError)):
        delivery.binding(proof, reference)


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "unpublished",
        "identity",
        "platform",
        "digest",
        "config",
        "tag",
        "extra",
    ],
)
def test_delivery_results_refused(tmp_path, fault):
    request, built, pushed, raw = documents(tmp_path)
    if fault == "missing":
        pushed.pop("schema")
    if fault == "unpublished":
        pushed["published"] = False
    if fault == "identity":
        pushed["image_id"] = "sha256:" + "0" * 64
    if fault == "platform":
        built["platform"] = pushed["platform"] = "other"
    if fault == "digest":
        pushed["manifest_digest"] = "sha256:" + "0" * 64
    if fault == "config":
        pushed["config_digest"] = "bad"
    if fault == "tag":
        built["tag"] = "x\nsecret"
    if fault == "extra":
        pushed["password"] = "secret"
    with pytest.raises((AttestError, ValueError)):
        delivery.results(
            delivery.canonical(built),
            delivery.canonical(pushed),
            request.expected_reference,
        )


def test_key_removed_on_native_failure(mocked, tmp_path, monkeypatch):
    monkeypatch.setattr(
        delivery, "run", lambda *a: (_ for _ in ()).throw(AttestError("failed"))
    )
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(AttestError):
        delivery.execute_attest(mocked, work)
    assert not list(work.rglob("*.key")) and not Path(mocked.output_dir).exists()


@pytest.mark.parametrize(
    "fault", ["inside", "symlink", "private", "special", "too-many"]
)
def test_independent_bounded_public_trust(tmp_path, fault):
    source = tmp_path / "trust"
    source.mkdir()
    if fault == "symlink":
        (source / "one.pub").symlink_to("/etc/passwd")
    if fault == "private":
        (source / "one.pub").write_text("PRIVATE KEY sentinel")
    if fault == "special":
        os.mkfifo(source / "one.pub")
    if fault == "too-many":
        for i in range(129):
            (source / f"{i}.pub").write_text("public")
    with pytest.raises((AttestError, OSError, BuildError)):
        delivery.trust_snapshot(
            source, tmp_path / "copy", source if fault == "inside" else None
        )


@pytest.mark.parametrize(
    "value",
    [
        "http://user:secret@host",
        "ftp://host",
        "https://host/?token=x",
        "https://host/#x",
    ],
)
def test_tsa_explicit_no_embedded_secrets(tmp_path, value):
    request, *_ = documents(tmp_path)
    with pytest.raises(ValueError):
        AttestRequest.model_validate(
            request.model_dump(by_alias=True) | {"tsa_url": value}
        )


def test_binary_hash_and_version(tmp_path):
    request, *_ = documents(tmp_path)
    with pytest.raises(AttestError, match="binary_mismatch"):
        delivery.tool(request, tmp_path, time.monotonic() + 5)
    executable = tmp_path / "wrong-version"
    executable.write_text("#!/bin/sh\necho attest 9.0.0\n")
    executable.chmod(0o700)
    data = request.model_dump(by_alias=True)
    data["tool"] = {
        "executable": str(executable),
        "version": "0.1.0",
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
    }
    with pytest.raises(AttestError, match="unsupported_attest_version"):
        delivery.tool(
            AttestRequest.model_validate(data), tmp_path, time.monotonic() + 5
        )


@pytest.mark.parametrize(
    "args,code",
    [
        (["-c", "import time;time.sleep(5)"], "attest_timeout"),
        (["-c", 'import sys;sys.stdout.write("s"*10000)'], "attest_output_limit"),
        (["-c", 'import sys;sys.stderr.write("secret"*10000)'], "attest_output_limit"),
        (["-c", "raise SystemExit(2)"], "attest_command_failed"),
    ],
)
def test_real_bounded_process_and_recovery(tmp_path, args, code):
    with pytest.raises(AttestError, match=code):
        run(Path(sys.executable), args, tmp_path, time.monotonic() + 0.3, 1024)
    assert (
        run(
            Path(sys.executable),
            ["-c", 'print("ok")'],
            tmp_path,
            time.monotonic() + 5,
            1024,
        )
        == b"ok\n"
    )


def test_native_missing_and_expired(tmp_path):
    with pytest.raises(AttestError, match="unavailable"):
        run(tmp_path / "missing", [], tmp_path, time.monotonic() + 1, 1024)
    with pytest.raises(AttestError, match="timeout"):
        run(Path(sys.executable), [], tmp_path, 0, 1024)


@pytest.mark.parametrize(
    "operation", ["attest", "verify", "unknown", "invalid", "oversized"]
)
def test_protocol_envelope_and_redaction(tmp_path, monkeypatch, capsys, operation):
    import io

    from apizr_attest import protocol

    request, *_ = documents(tmp_path)
    reply = delivery.DeliveryResult(
        reference=request.expected_reference,
        manifest_digest=request.expected_reference.split("@")[1],
        signer="3" * 64,
        receipt_sha256="4" * 64,
        checks=dict.fromkeys(delivery.CHECKS, "pass"),
    )
    monkeypatch.setattr(protocol, "execute_attest", lambda *a: reply)
    monkeypatch.setattr(protocol, "execute_verify", lambda *a: reply)
    arguments = request.model_dump(by_alias=True)
    if operation == "verify":
        arguments = {
            **request.model_dump(
                include={"expected_reference", "expected_signer", "trust_store", "tool"}
            ),
            "schema": "apizr.verify-delivery/v1",
            "proof_dir": str(tmp_path),
        }
    payload = json.dumps(
        {
            "protocol": "apizr.extension/v1",
            "request_id": "0" * 32,
            "operation": operation,
            "arguments": arguments,
        }
    ).encode()
    if operation == "invalid":
        payload = b"{secret"
    if operation == "oversized":
        payload = b" " * 1048577
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload)))
    code = protocol.main()
    out = capsys.readouterr()
    assert "secret" not in out.out + out.err
    if operation in {"invalid", "oversized"}:
        assert code == 2
    else:
        assert json.loads(out.out)["status"] == (
            "ok" if operation in {"attest", "verify"} else "error"
        )


def test_python_api_uses_cancellable_runtime(tmp_path, monkeypatch):
    from threading import Event
    from types import SimpleNamespace

    from apizr_attest import api

    request, *_ = documents(tmp_path)
    cancel = Event()
    reply = delivery.DeliveryResult(
        reference=request.expected_reference,
        manifest_digest=request.expected_reference.split("@")[1],
        signer="3" * 64,
        receipt_sha256="4" * 64,
        checks=dict.fromkeys(delivery.CHECKS, "pass"),
    )

    def invoke(python, module, operation, arguments, **kwargs):
        assert python == sys.executable and module == "apizr_attest.protocol"
        assert kwargs["environment"] == {} and kwargs["cancel"] is cancel
        return SimpleNamespace(result=reply.model_dump(by_alias=True))

    monkeypatch.setattr(api, "invoke_extension", invoke)
    assert api.attest(request, cancel=cancel) == reply
    verify = VerifyRequest.model_validate(
        {
            **request.model_dump(
                include={"expected_reference", "expected_signer", "trust_store", "tool"}
            ),
            "schema": "apizr.verify-delivery/v1",
            "proof_dir": str(tmp_path),
        }
    )
    assert api.verify(verify, cancel=cancel) == reply

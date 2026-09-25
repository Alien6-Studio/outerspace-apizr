"""Private worker implementation; all callers use the extension runtime."""

import hashlib
import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from apizr_oci.model import BuildResult, PushRequest, PushResult
from apizr_oci.observe import observe
from apizr_oci.push import document
from apizr_oci.snapshot import read

from apizr.local_plugins.store import installation_lock

from .model import AttestError, AttestRequest, Common, DeliveryResult, VerifyRequest
from .process import run

CHECKS = {"schema", "consistency", "signature", "timestamp", "recompute"}
SCOPE = "verified OCI delivery; build not supervised by Attest"
PIPELINE = b"""version: "0.1"
name: "apizr-oci-delivery"
steps:
  bind-verified-delivery:
    run: "true"
    inputs: ["delivery/"]
    outputs: ["delivery/"]
    attestation:
      type: "verified-oci-delivery"
"""
FILES = (
    "attest.yaml",
    "receipt.yaml",
    "delivery/build.json",
    "delivery/push.json",
    "delivery/oci-manifest.json",
    "delivery/manifest.json",
)
MAX_FILE = 1048576


def canonical(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def file_bytes(path: str, limit=MAX_FILE) -> bytes:
    selected = Path(path)
    return read(selected.parent, selected.name, limit)


def write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(path, "xb", opener=lambda p, f: os.open(p, f, 0o600)) as output:
        output.write(raw)


def tool(request: Common, work: Path, deadline: float) -> Path:
    if not os.access(request.tool.executable, os.X_OK):
        raise AttestError("attest_unavailable")
    raw = file_bytes(request.tool.executable, 128 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != request.tool.sha256:
        raise AttestError("attest_binary_mismatch")
    executable = work / "attest-bin"
    write(executable, raw)
    executable.chmod(0o700)
    if run(executable, ["--version"], work, deadline, 1024).strip() != b"attest 0.1.0":
        raise AttestError("unsupported_attest_version")
    return executable


def trust_snapshot(source: Path, target: Path, proof: Path | None = None) -> None:
    if proof is not None and source.resolve().is_relative_to(proof.resolve()):
        raise AttestError("independent_trust_required")
    # Only public keys, the native policy and pinned TSA certificates. No fallback
    # to workspace keys or a receipt-supplied store. Never modify the source.
    target.mkdir(mode=0o700)
    total = 0
    count = 0
    for parent, suffix in ((source, ""), (source / "tsa", "tsa/")):
        if suffix and not parent.exists():
            continue
        if parent.is_symlink() or not parent.is_dir():
            raise AttestError("invalid_trust_store")
        for path in parent.iterdir():
            if not suffix and path.name == "tsa":
                continue
            count += 1
            if count > 128 or not (
                path.suffix == (".crt" if suffix else ".pub")
                or (not suffix and path.name == "trust.toml")
            ):
                raise AttestError("invalid_trust_store")
            raw = read(source, suffix + path.name, min(MAX_FILE, 4 * MAX_FILE - total))
            total += len(raw)
            if b"PRIVATE KEY" in raw:
                raise AttestError("invalid_trust_store")
            write(target / suffix / path.name, raw)


def validate_verdict(report, expected_signer: str) -> None:
    if not isinstance(report, dict):
        raise AttestError("receipt_verification_failed")
    checks = report.get("checks")
    if (
        report.get("verdict") != "pass"
        or report.get("signed_by") != expected_signer
        or report.get("warnings") != []
        or not isinstance(checks, list)
        or len(checks) != len(CHECKS)
        or any(not isinstance(c, dict) for c in checks)
        or {c.get("name") for c in checks} != CHECKS
        or any(c.get("status") != "pass" for c in checks)
    ):
        raise AttestError("receipt_verification_failed")


def results(build_raw: bytes, push_raw: bytes, reference: str):
    built, pushed = document(build_raw), document(push_raw)
    if (
        not isinstance(built, dict)
        or not isinstance(pushed, dict)
        or built.get("schema") != "apizr.oci-build-result/v1"
        or pushed.get("schema") != "apizr.oci-push-result/v1"
        or built.get("published") is not False
        or pushed.get("published") is not True
    ):
        raise AttestError("invalid_delivery_results")
    build = BuildResult.model_validate(built)
    push = PushResult.model_validate(pushed)
    if (
        push.digest_reference != reference
        or push.index_digest is not None
        or push.destination.rsplit(":", 1)[0] != reference.split("@")[0]
        or reference.split("@")[1] != push.manifest_digest
        or any(
            getattr(build, k) != getattr(push, k)
            for k in ("image_id", "platform", "inputs_sha256")
        )
    ):
        raise AttestError("delivery_identity_mismatch")
    # Reuse the install/push input validators, without storing operational params.
    import re

    if (
        push.platform not in {"linux/amd64", "linux/arm64"}
        or re.fullmatch(r"[0-9a-f]{64}", push.inputs_sha256) is None
        or any(
            re.fullmatch(r"sha256:[0-9a-f]{64}", d) is None
            for d in (push.image_id, push.manifest_digest, push.config_digest)
        )
        or push.image_id not in {push.manifest_digest, push.config_digest}
    ):
        raise AttestError("delivery_identity_mismatch")
    PushRequest.reference(push.destination)
    # Local tag is a historical declaration, not an authority or a command.
    if len(build.tag) > 255 or any(ord(c) < 32 for c in build.tag):
        raise AttestError("invalid_delivery_results")
    return build, push


def manifest(reference: str, files: dict[str, bytes]) -> bytes:
    return canonical(
        {
            "schema": "apizr.oci-delivery/v1",
            "scope": SCOPE,
            "reference": reference,
            "verified": [
                "local image identity, platform and inputs label",
                "remote manifest bytes and configuration identity",
            ],
            "declared": [
                "inputs_sha256 originates from the build; not recomputed from this receipt",
                "build tag is historical; no Git or build-supervision claim",
            ],
            "files": {
                name: hashlib.sha256(raw).hexdigest()
                for name, raw in sorted(files.items())
            },
        }
    )


def binding(work: Path, reference: str) -> None:
    if read(work, "attest.yaml", MAX_FILE) != PIPELINE:
        raise AttestError("unexpected_delivery_pipeline")
    files = {
        name: read(work, "delivery/" + name, MAX_FILE)
        for name in ("build.json", "push.json", "oci-manifest.json")
    }
    _, pushed = results(files["build.json"], files["push.json"], reference)
    raw = files["oci-manifest.json"]
    if "sha256:" + hashlib.sha256(raw).hexdigest() != pushed.manifest_digest:
        raise AttestError("manifest_digest_mismatch")
    native = document(raw)
    if native["config"]["digest"] != pushed.config_digest:
        raise AttestError("config_digest_mismatch")
    if read(work, "delivery/manifest.json", MAX_FILE) != manifest(reference, files):
        raise AttestError("delivery_manifest_mismatch")


def verified(
    request: Common, executable: Path, proof: Path, trust: Path, deadline: float
) -> DeliveryResult:
    binding(proof, request.expected_reference)
    report = document(
        run(
            executable,
            [
                "verify",
                "receipt.yaml",
                "--recompute",
                "--workspace",
                str(proof),
                "--trust-store",
                str(trust),
                "--offline",
                "--format",
                "json",
            ],
            proof,
            deadline,
            request.max_output_bytes,
        )
    )
    validate_verdict(report, request.expected_signer)
    return DeliveryResult(
        reference=request.expected_reference,
        manifest_digest=request.expected_reference.split("@")[1],
        signer=request.expected_signer,
        receipt_sha256=hashlib.sha256(
            read(proof, "receipt.yaml", MAX_FILE)
        ).hexdigest(),
        checks=dict.fromkeys(sorted(CHECKS), "pass"),
    )


def execute_verify(request: VerifyRequest, work: Path) -> DeliveryResult:
    deadline = time.monotonic() + request.timeout_ms / 1000
    source = Path(request.proof_dir)
    proof = work / "proof"
    snapshot(source, proof)
    trust = work / "trust"
    trust_snapshot(Path(request.trust_store), trust, source)
    executable = tool(request, work, deadline)
    return verified(request, executable, proof, trust, deadline)


def execute_attest(request: AttestRequest, work: Path) -> DeliveryResult:
    deadline = time.monotonic() + request.timeout_ms / 1000
    output = Path(request.output_dir)
    if os.path.lexists(output):
        raise AttestError("proof_already_exists")
    executable = tool(request, work, deadline)
    trust = work / "trust"
    trust_snapshot(Path(request.trust_store), trust, output)
    build, pushed = results(
        file_bytes(request.build_result),
        file_bytes(request.push_result),
        request.expected_reference,
    )
    observation = observe(
        PushRequest.model_validate(
            {
                "schema": "apizr.oci-push/v1",
                "image_id": pushed.image_id,
                "platform": pushed.platform,
                "inputs_sha256": pushed.inputs_sha256,
                "destination": pushed.destination,
                "docker": request.docker.model_dump(),
                "authentication": request.authentication.model_dump(),
                "timeout_ms": max(1, int((deadline - time.monotonic()) * 1000)),
                "max_log_bytes": request.max_output_bytes,
            }
        ),
        request.expected_reference,
        workspace=work,
    )
    if (
        len(observation.manifest) > MAX_FILE
        or observation.manifest_digest != pushed.manifest_digest
        or observation.config_digest != pushed.config_digest
    ):
        raise AttestError("delivery_identity_mismatch")
    proof = work / "proof"
    files = {
        "build.json": canonical(build.model_dump(by_alias=True)),
        "push.json": canonical(pushed.model_dump(by_alias=True)),
        "oci-manifest.json": observation.manifest,
    }
    for name, raw in files.items():
        write(proof / "delivery" / name, raw)
    write(proof / "delivery/manifest.json", manifest(request.expected_reference, files))
    write(proof / "attest.yaml", PIPELINE)
    key = proof / ".attest/keys" / (request.key_id + ".key")
    try:
        write(key, file_bytes(request.key_file, 16384))
        run(
            executable,
            [
                "run",
                "--pipeline",
                "attest.yaml",
                "--sign",
                "--timestamp",
                "--key",
                request.key_id,
                "--tsa",
                request.tsa_url,
            ],
            proof,
            deadline,
            request.max_output_bytes,
        )
    finally:
        key.unlink(missing_ok=True)
    receipts = list((proof / ".attest/receipts").glob("*.yaml"))
    if len(receipts) != 1:
        raise AttestError("fresh_receipt_required")
    write(proof / "receipt.yaml", read(receipts[0].parent, receipts[0].name, MAX_FILE))
    result = verified(request, executable, proof, trust, deadline)
    export(proof, output)
    return result


def snapshot(source: Path, target: Path) -> None:
    for name in FILES:
        write(target / name, read(source, name, MAX_FILE))


def export(proof: Path, output: Path) -> None:
    # Publish only the public allowlist, after full validation, under the existing
    # cooperative lock. The parent must be user-owned and not group/world writable.
    with installation_lock(output.parent):
        if os.path.lexists(output):
            raise AttestError("proof_already_exists")
        with TemporaryDirectory(
            prefix=".attest-export-", dir=output.parent
        ) as directory:
            stage = Path(directory) / "proof"
            for name in FILES:
                write(stage / name, read(proof, name, MAX_FILE))
            stage.rename(output)

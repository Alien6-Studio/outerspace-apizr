"""Writer half of the real OCI proof; imported by the existing Attest fixture."""

import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

FILES = (
    "attest.yaml",
    "receipt.yaml",
    "delivery/build.json",
    "delivery/push.json",
    "delivery/oci-manifest.json",
    "delivery/manifest.json",
)


def exercise(python, store, work, first, second, signing, command, environment):
    oras = Path("/opt/oras/oras")
    transport = {
        "tool": {
            "executable": str(oras),
            "version": "1.3.4",
            "sha256": hashlib.sha256(oras.read_bytes()).hexdigest(),
        },
        "authentication": signing["authentication"],
    }
    assert (
        transport["tool"]["sha256"]
        == "246c47e91bf2749a555ffe00a9824844c6df3a26d61974e3ce08f2077d79c556"
    )
    common = {
        key: signing[key]
        for key in ("expected_reference", "expected_signer", "trust_store", "tool")
    }
    auth = json.loads(Path("/proof/auth/config.json").read_text())["auths"][
        "registry.test:5443"
    ]["auth"]
    secrets = (auth.encode(), base64.b64decode(auth).split(b":", 1)[1])
    base = [
        str(python),
        "-I",
        "-B",
        "-m",
        "apizr.cli",
        "plugins",
        "run",
        "apizr-attest",
    ]
    refusals = []

    def invoke(op, data, refused=False):
        path = work / (op + "-artifact.json")
        path.write_text(json.dumps(data))
        result = subprocess.run(
            [
                *base,
                op,
                "--arguments",
                str(path),
                "--plugins-dir",
                str(store),
                "--timeout-ms",
                "360000",
            ],
            cwd=work,
            env=environment,
            capture_output=True,
            timeout=365,
        )
        assert not any(secret in result.stdout + result.stderr for secret in secrets)
        if refused:
            assert result.returncode == 2 and result.stdout == b"", (
                result.stdout,
                result.stderr,
            )
            return {}
        assert result.returncode == 0, (result.stdout, result.stderr)
        return json.loads(result.stdout)["result"]

    discovery = {
        "schema": "apizr.discover-proofs/v1",
        "expected_reference": common["expected_reference"],
        "transport": transport,
    }
    assert invoke("discover", discovery)["candidates"] == []
    before = command(
        "/usr/local/bin/docker",
        "--host",
        "unix:///proof/builder.sock",
        "image",
        "inspect",
        json.loads((first / "delivery/build.json").read_text())["image_id"],
    )
    publish = common | {
        "schema": "apizr.publish-proof/v1",
        "proof_dir": str(first),
        "transport": transport,
    }
    wrong = publish | {"expected_signer": "0" * 64}
    invoke("publish", wrong, True)
    refusals.append("invalid-proof-before-publication")
    one = invoke("publish", publish)
    assert invoke("publish", publish) == one
    two = invoke("publish", publish | {"proof_dir": str(second)})
    assert one["artifact_reference"] != two["artifact_reference"]
    found = invoke("discover", discovery)
    assert len(found["candidates"]) == 2 and all(
        not c["verified"] for c in found["candidates"]
    )
    assert [c["reference"] for c in found["candidates"]] == sorted(
        c["reference"] for c in found["candidates"]
    )
    invoke(
        "discover", discovery | {"transport": transport | {"max_candidates": 1}}, True
    )
    refusals.append("candidate-limit-not-empty-or-truncated")
    bad = work / "denied-auth.json"
    bad.write_text(
        json.dumps(
            {
                "auths": {
                    "registry.test:5443": {
                        "auth": base64.b64encode(b"fixture:wrong").decode()
                    }
                }
            }
        )
    )
    for change in (
        {"config_file": str(bad), "ca_file": "/proof/certs/ca.crt"},
        {"config_file": "/proof/auth/config.json"},
    ):
        invoke(
            "discover",
            discovery | {"transport": transport | {"authentication": change}},
            True,
        )
    refusals.extend(["authentication-not-empty", "tls-not-empty"])
    after = command(
        "/usr/local/bin/docker",
        "--host",
        "unix:///proof/builder.sock",
        "image",
        "inspect",
        json.loads((first / "delivery/build.json").read_text())["image_id"],
    )
    assert before == after
    flags = [
        "--registry-config",
        "/proof/auth/config.json",
        "--ca-file",
        "/proof/certs/ca.crt",
    ]
    direct = json.loads(
        command(
            oras,
            "discover",
            "--distribution-spec",
            "v1.1-referrers-api",
            "--depth",
            "1",
            "--format",
            "json",
            "--artifact-type",
            "application/vnd.apizr.attest.delivery.v1",
            common["expected_reference"],
            *flags,
        )
    )
    assert {c["digest"] for c in direct["referrers"]} == {
        one["artifact_manifest_digest"],
        two["artifact_manifest_digest"],
    }
    native = work / "direct-oras-pull"
    native.mkdir()
    command(oras, "pull", one["artifact_reference"], "--output", native, *flags)
    hashes = {n: hashlib.sha256((first / n).read_bytes()).hexdigest() for n in FILES}
    assert hashes == {
        n: hashlib.sha256((native / n).read_bytes()).hexdigest() for n in FILES
    }
    # A transparent observer executes real ORAS, then injects a confirmation
    # failure or blocks after the successful remote attach for cancellation.
    import signal
    import tempfile
    import time

    observer = work / "oras-observer"
    shutil.copyfile("/repo/scripts/oras_transfer_observer.py", observer)
    observer.chmod(0o700)
    observed = publish | {
        "transport": transport
        | {
            "tool": transport["tool"]
            | {
                "executable": str(observer),
                "sha256": hashlib.sha256(observer.read_bytes()).hexdigest(),
            }
        }
    }
    marker = work / "observed-attach.json"
    for mode in ("confirmation", "interruption"):
        marker.unlink(missing_ok=True)
        (work / "oras-observer-mode").write_text(mode)
        if mode == "confirmation":
            uncertain = invoke("publish", observed)
            assert uncertain["state"] == "remote_state_unconfirmed"
            assert uncertain["receipt_published"] is False
            assert uncertain["artifact_reference"] is None
        else:
            argument = work / "interrupted-publish.json"
            argument.write_text(json.dumps(observed))
            with tempfile.TemporaryDirectory(dir=work) as runtimes:
                process = subprocess.Popen(
                    [
                        *base,
                        "publish",
                        "--arguments",
                        str(argument),
                        "--plugins-dir",
                        str(store),
                        "--timeout-ms",
                        "360000",
                    ],
                    cwd=work,
                    env=environment | {"TMPDIR": runtimes},
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    deadline = time.monotonic() + 30
                    while not marker.exists():
                        assert process.poll() is None and time.monotonic() < deadline
                        time.sleep(0.02)
                    process.send_signal(signal.SIGINT)
                    stdout, stderr = process.communicate(timeout=10)
                    assert process.returncode == 130 and not stdout, stderr
                    assert not any(secret in stderr for secret in secrets)
                    assert not list(Path(runtimes).iterdir())
                finally:
                    (work / "oras-observer-release").touch()
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=5)
        assert (
            json.loads(marker.read_bytes())["digest"] == one["artifact_manifest_digest"]
        )
        assert invoke("publish", publish) == one
        refusals.append(mode + "-after-real-attach-with-recovery")
    # An external publisher can attach an invalid receipt. Discovery must not
    # bless it, and fetch must reject it despite valid OCI hashes and subject.
    malicious = work / "invalid-native-proof"
    shutil.copytree(first, malicious)
    receipt = malicious / "receipt.yaml"
    receipt.write_text(
        receipt.read_text().replace("pipeline_hash:", "pipeline_hash: invalid #", 1)
    )
    direct_result = subprocess.run(
        [
            str(oras),
            "attach",
            "--distribution-spec",
            "v1.1-referrers-api",
            "--artifact-type",
            "application/vnd.apizr.attest.delivery.v1",
            "--annotation",
            "org.opencontainers.image.created=1970-01-01T00:00:00Z",
            "--concurrency",
            "1",
            "--format",
            "json",
            common["expected_reference"],
            *[
                n + ":application/vnd.apizr.attest.delivery.file.v1"
                for n in sorted(FILES)
            ],
            *flags,
        ],
        cwd=malicious,
        capture_output=True,
        timeout=60,
    )
    assert direct_result.returncode == 0, direct_result.stderr
    invalid_reference = json.loads(direct_result.stdout)["reference"]
    shutil.rmtree(malicious)
    # Verify registry-side read-only authorization directly, before the gateway.
    read_flags = [
        "--registry-config",
        "/proof/auth/read-config.json",
        "--ca-file",
        "/proof/certs/ca.crt",
    ]
    read_candidates = json.loads(
        command(
            oras,
            "discover",
            "--distribution-spec",
            "v1.1-referrers-api",
            "--depth",
            "1",
            "--format",
            "json",
            common["expected_reference"],
            *read_flags,
        )
    )
    assert len(read_candidates["referrers"]) == 3
    denied = subprocess.run(
        [
            str(oras),
            "attach",
            "--distribution-spec",
            "v1.1-referrers-api",
            "--artifact-type",
            "application/vnd.apizr.test.refused",
            common["expected_reference"],
            "receipt.yaml",
            *read_flags,
        ],
        cwd=first,
        capture_output=True,
        timeout=30,
    )
    assert denied.returncode != 0 and any(
        code in denied.stderr.lower()
        for code in (b"403", b"401", b"denied", b"unauthorized")
    ), denied.stderr
    refusals.append("registry-reader-credential-cannot-publish")
    consumer = Path("/proof/artifact-consumer")
    consumer.mkdir(mode=0o700)
    shutil.copytree(work / "attest-wheels", consumer / "wheels")
    shutil.copytree(Path(common["trust_store"]), consumer / "trust")
    shutil.copyfile("/proof/auth/read-config.json", consumer / "auth.json")
    shutil.copyfile("/proof/certs/ca.crt", consumer / "ca.crt")
    # Neither proof nor private key nor Docker socket enters this volume subtree.
    record = {
        "publish": one,
        "other": two,
        "invalid_reference": invalid_reference,
        "hashes": hashes,
        "transport": transport,
        "common": common,
    }
    (consumer / "input.json").write_text(json.dumps(record))
    (work / "artifact-results.json").write_text(
        json.dumps(
            {
                "published": one,
                "second": two,
                "discovered": found,
                "oras": transport["tool"],
                "same_bytes": True,
                "image_unchanged": True,
            },
            indent=2,
        )
    )
    (work / "artifact-refusals.json").write_text(json.dumps(refusals))
    shutil.rmtree(native)
    print(
        "PASS ORAS attach/discover/pull interop, idempotent verified publication and two independent receipts",
        flush=True,
    )

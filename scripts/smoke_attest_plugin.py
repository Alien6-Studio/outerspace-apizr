"""Installed-wheel, real Attest/TSA proof, inside the disposable OCI fixture."""

import hashlib
import json
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from threading import Event

from attest_test_authority import authority
from attest_test_authority import command as native_command
from smoke_oci_plugin import REPO, lock_wheels


def exercise(python, store, work, builds, command, environment):
    house = work / "attest-wheels"
    shutil.copytree(work / "plugin-wheels", house)
    command("uv", "build", "--wheel", REPO / "plugins/attest", "--out-dir", house)
    lock = work / "attest.lock"
    lock_wheels(house, lock)
    wheel = next(house.glob("apizr_attest-*.whl"))
    base = [str(python), "-I", "-B", "-m", "apizr.cli", "plugins"]
    command(
        *base,
        "install",
        wheel,
        "--sha256",
        hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "--requirements",
        lock,
        "--wheelhouse",
        house,
        "--plugins-dir",
        store,
    )
    command(
        *base, "enable", "apizr-attest", "--version", "0.0.0", "--plugins-dir", store
    )
    native = Path("/opt/attest/attest")
    tool = {
        "executable": str(native),
        "version": "0.1.0",
        "sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
    }
    assert (
        tool["sha256"]
        == "c73ecb92a2ebbf324cb0bdcf631fc3505f3395aa1acad30501284156cef9ce35"
    )
    (work / "attest-tool.json").write_text(json.dumps(tool))
    keys = work / "test-identity"
    keys.mkdir(mode=0o700)
    native_command(
        native, "keys", "generate", "--name", "Disposable OCI delivery test", cwd=keys
    )
    key = next((keys / ".attest/keys").glob("*.key"))
    # Decode only the TEST public key to supply its independent expected identity.
    public = subprocess.run(
        [
            "openssl",
            "pkey",
            "-pubin",
            "-in",
            str(keys / ".attest/trust" / (key.stem + ".pub")),
            "-outform",
            "DER",
        ],
        capture_output=True,
        check=True,
        timeout=10,
    ).stdout
    signer = public[-32:].hex()
    trust = work / "independent-trust"
    shutil.copytree(keys / ".attest/trust", trust)
    pushes = json.loads((work / "push-results.json").read_text())
    build = work / "attest-build.json"
    build.write_text(json.dumps(builds[0]["result"]))
    push = work / "attest-push.json"
    push.write_text(json.dumps(pushes[0]))
    output = work / "delivery-proof"
    refusals = []
    secrets = [
        key.read_bytes(),
        json.loads(Path("/proof/auth/config.json").read_text())["auths"][
            "registry.test:5443"
        ]["auth"].encode(),
    ]

    def invoke(operation, arguments, *, refused=False, offline=False):
        argsfile = work / f"{operation}-arguments.json"
        argsfile.write_text(json.dumps(arguments))
        args = [
            *base,
            "run",
            "apizr-attest",
            operation,
            "--arguments",
            str(argsfile),
            "--plugins-dir",
            str(store),
            "--timeout-ms",
            "360000",
        ]
        if offline:
            args = ["unshare", "--net", *args]
        result = subprocess.run(
            args, cwd=work, env=environment, capture_output=True, timeout=365
        )
        assert not any(s in result.stdout + result.stderr for s in secrets)
        if refused:
            assert result.returncode == 2 and result.stdout == b"", (
                result.returncode,
                result.stdout,
                result.stderr,
            )
            return None
        assert result.returncode == 0, (result.stdout, result.stderr)
        return json.loads(result.stdout)["result"]

    with authority(work / "test-tsa") as (url, ca, calls):
        (trust / "tsa").mkdir()
        shutil.copyfile(ca, trust / "tsa/local.crt")
        arguments = {
            "schema": "apizr.attest-delivery/v1",
            "build_result": str(build),
            "push_result": str(push),
            "expected_reference": pushes[0]["digest_reference"],
            "expected_signer": signer,
            "docker": {
                "executable": "/usr/local/bin/docker",
                "socket": "/proof/builder.sock",
            },
            "authentication": {
                "config_file": "/proof/auth/config.json",
                "ca_file": "/proof/certs/ca.crt",
            },
            "tool": tool,
            "trust_store": str(trust),
            "key_file": str(key),
            "key_id": key.stem,
            "tsa_url": url,
            "output_dir": str(output),
            "timeout_ms": 300000,
        }
        for name, change in (
            ("wrong-reference", {"expected_reference": pushes[1]["digest_reference"]}),
            ("wrong-signer", {"expected_signer": "0" * 64}),
            ("missing-attest", {"tool": tool | {"executable": "/missing/attest"}}),
            ("wrong-version", {"tool": tool | {"version": "9.0.0"}}),
            ("wrong-hash", {"tool": tool | {"sha256": "0" * 64}}),
        ):
            invoke("attest", arguments | change, refused=True)
            assert not output.exists()
            refusals.append({"case": name, "refused": True})
        # An external writer moves the mutable tag. Digest observation must still
        # attest the original REST image, without changing that tag again.
        docker = [
            "/usr/local/bin/docker",
            "--config",
            "/proof/auth",
            "--host",
            "unix:///proof/builder.sock",
        ]
        command(
            *docker,
            "image",
            "tag",
            builds[1]["result"]["image_id"],
            pushes[0]["destination"],
        )
        command(
            *docker,
            "image",
            "push",
            "--platform",
            builds[1]["result"]["platform"],
            pushes[0]["destination"],
        )
        signed = invoke("attest", arguments)
        assert signed is not None
        assert signed["checks"] == dict.fromkeys(
            ["schema", "consistency", "signature", "timestamp", "recompute"], "pass"
        )
        assert calls
        invoke("attest", arguments, refused=True)  # never overwrite
        # Synchronize cancellation on an actual RFC3161 request, while a private
        # copy of the signing key exists. The core owns all ordinary descendants.
        received, release = Event(), Event()
        with authority(work / "blocked-tsa", received=received, release=release) as (
            blocked_url,
            blocked_ca,
            _,
        ):
            shutil.copyfile(blocked_ca, trust / "tsa/blocked.crt")
            blocked = arguments | {
                "tsa_url": blocked_url,
                "output_dir": str(work / "interrupted-proof"),
            }
            blocked_file = work / "blocked-arguments.json"
            blocked_file.write_text(json.dumps(blocked))
            with tempfile.TemporaryDirectory(dir=work) as runtimes:
                process = subprocess.Popen(
                    [
                        *base,
                        "run",
                        "apizr-attest",
                        "attest",
                        "--arguments",
                        str(blocked_file),
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
                    assert received.wait(30), "signer did not reach local TSA"
                    assert list(Path(runtimes).rglob("*.key"))
                    process.send_signal(signal.SIGINT)
                    stdout, stderr = process.communicate(timeout=10)
                    assert process.returncode == 130 and not stdout
                    assert not any(secret in stderr for secret in secrets)
                    assert not list(Path(runtimes).iterdir())
                    assert not (work / "interrupted-proof").exists()
                    refusals.append(
                        {"case": "interruption-key-cleanup", "refused": True}
                    )
                finally:
                    release.set()
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=5)
        recovered = arguments | {"output_dir": str(work / "recovered-proof")}
        assert invoke("attest", recovered) is not None
        shutil.rmtree(work / "recovered-proof")
        copied = work / "transported-proof"
        shutil.copytree(output, copied)
        shutil.rmtree(output)
        shutil.rmtree(keys)
        for path in copied.rglob("*"):
            if path.is_file():
                raw = path.read_bytes()
                assert not any(s in raw for s in secrets) and b"PRIVATE KEY" not in raw
        verification = {
            "schema": "apizr.verify-delivery/v1",
            "proof_dir": str(copied),
            "expected_reference": arguments["expected_reference"],
            "expected_signer": signer,
            "trust_store": str(trust),
            "tool": tool,
        }
        before_calls = len(calls)
        verified = invoke("verify", verification, offline=True)
        assert verified is not None
        assert signed == verified and len(calls) == before_calls
        assert verified["registry_availability_verified"] is False
        for name in (
            "manifest",
            "push",
            "receipt",
            "other-image",
            "signer",
            "untrusted-key",
            "revoked-key",
            "untrusted-tsa",
            "missing-timestamp",
            "invalid-timestamp",
            "proof-trust",
        ):
            altered = work / "altered-proof"
            shutil.copytree(copied, altered)
            independent = work / "altered-trust"
            shutil.copytree(trust, independent)
            selected = verification | {
                "proof_dir": str(altered),
                "trust_store": str(independent),
            }
            if name in {"manifest", "push", "receipt"}:
                path = (
                    altered
                    / {
                        "manifest": "delivery/oci-manifest.json",
                        "push": "delivery/push.json",
                        "receipt": "receipt.yaml",
                    }[name]
                )
                if name == "receipt":
                    path.write_text(
                        path.read_text().replace(
                            "pipeline_hash:", "pipeline_hash: invalid #", 1
                        )
                    )
                else:
                    path.write_bytes(path.read_bytes() + b" ")
            if name == "other-image":
                selected["expected_reference"] = pushes[1]["digest_reference"]
            if name == "signer":
                selected["expected_signer"] = "0" * 64
            if name == "untrusted-key":
                next(independent.glob("*.pub")).unlink()
            if name == "revoked-key":
                (independent / "trust.toml").write_text(
                    f'version = 1\n[[key]]\nid = "{key.stem}"\nname = "revoked test"\nstatus = "revoked"\n'
                )
            if name == "untrusted-tsa":
                shutil.rmtree(independent / "tsa")
            if name in {"missing-timestamp", "invalid-timestamp"}:
                path = altered / "receipt.yaml"
                lines = path.read_text().splitlines()
                assert any(line.startswith("timestamp_token:") for line in lines)
                path.write_text(
                    "\n".join(
                        line
                        for line in lines
                        if not line.startswith("timestamp_token:")
                    )
                    + "\n"
                    + (
                        "timestamp_token: invalid\n"
                        if name == "invalid-timestamp"
                        else ""
                    )
                )
            if name == "proof-trust":
                shutil.copytree(trust, altered / "trust")
                selected["trust_store"] = str(altered / "trust")
            invoke("verify", selected, refused=True, offline=True)
            refusals.append({"case": name, "refused": True})
            shutil.rmtree(altered)
            shutil.rmtree(independent)
            assert invoke("verify", verification, offline=True) == verified
        (work / "attest-results.json").write_text(
            json.dumps(
                {
                    "signed": signed,
                    "verified_offline": verified,
                    "tsa_calls": len(calls),
                    "private_key_removed": True,
                },
                indent=2,
            )
        )
        (work / "attest-refusals.json").write_text(json.dumps(refusals, indent=2))
    print(
        "PASS real Attest signature, local RFC3161 timestamp, transported offline verification without network or private key",
        flush=True,
    )

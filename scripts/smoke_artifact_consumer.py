"""Consumer fixture: read-only TLS gateway, no Docker socket, then no network."""

import json
import subprocess
from pathlib import Path


def consume(command, output, prefix, network, volume, image, repo):
    reader_net = prefix + "-reader-net"
    proxy = prefix + "-reader-proxy"
    command("docker", "network", "create", reader_net)
    try:
        # The gateway enforces read-only methods and forwards to real Zot.
        command(
            "docker",
            "run",
            "--detach",
            "--name",
            proxy,
            "--network",
            network,
            "--mount",
            f"type=volume,src={volume},dst=/proof",
            "--mount",
            f"type=bind,src={repo},dst=/repo,readonly",
            "--entrypoint",
            "python3",
            image,
            "/repo/scripts/artifact_registry_gateway.py",
        )
        command(
            "docker",
            "network",
            "connect",
            "--alias",
            "registry.test",
            reader_net,
            proxy,
        )
        for offline in (False, True):
            args = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none" if offline else reader_net,
                "--entrypoint",
                "python3",
                "--mount",
                f"type=volume,src={volume},dst=/consumer,volume-subpath=artifact-consumer",
                "--mount",
                f"type=bind,src={repo},dst=/repo,readonly",
                image,
                "/repo/scripts/smoke_artifact_consumer.py",
                "--offline" if offline else "--fetch",
            ]
            result = command(*args)
            (
                output / ("artifact-offline.log" if offline else "artifact-fetch.log")
            ).write_text(result)
        # Retain only public verification results, never reader credentials.
        result = command(
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "python3",
            "--mount",
            f"type=volume,src={volume},dst=/proof,readonly",
            image,
            "-c",
            'print(open("/proof/artifact-consumer/result.json").read())',
        )
        (output / "artifact-fetch-result.json").write_text(result)
    finally:
        subprocess.run(
            ["docker", "rm", "--force", proxy], capture_output=True, timeout=30
        )
        command("docker", "network", "rm", reader_net)


def main():
    import hashlib
    import os
    import shutil
    import sys

    from smoke_oci_plugin import lock_wheels, run

    root = Path("/consumer")
    os.chdir(root)
    record = json.loads((root / "input.json").read_text())

    def command(*args):
        return run(
            args,
            cwd=root,
            env=dict(
                os.environ, PYTHONDONTWRITEBYTECODE="1", UV_PYTHON_DOWNLOADS="never"
            ),
        )

    python = root / "core/bin/python"
    store = root / "plugins"

    def cli(*args):
        return command(python, "-I", "-B", "-m", "apizr.cli", "plugins", *args)

    if sys.argv[1] == "--offline":
        Path("/opt/oras/oras").unlink()
        assert not (root / "auth.json").exists()
        result = json.loads(
            cli(
                "run",
                "apizr-attest",
                "verify",
                "--arguments",
                root / "verify.json",
                "--plugins-dir",
                store,
                "--timeout-ms",
                "180000",
            )
        )
        assert all(v == "pass" for v in result["result"]["checks"].values())
        print(
            "PASS offline verification without ORAS, registry credentials, Docker socket or private key"
        )
        return
    assert (
        not Path("/var/run/docker.sock").exists()
        and not Path("/proof/builder.sock").exists()
    )
    assert not list(root.rglob("*.key"))
    house = root / "wheels"
    core = next(house.glob("outerspace_apizr-*.whl"))
    plugin = next(house.glob("apizr_attest-*.whl"))
    command("uv", "venv", "--python", sys.executable, root / "core")
    command(
        "uv",
        "pip",
        "install",
        "--python",
        python,
        "--offline",
        "--no-index",
        "--find-links",
        house,
        core,
    )
    from smoke_extension_packaging import snapshot

    before = snapshot(root / "core")
    lock_wheels(house, root / "plugins.lock")
    cli(
        "install",
        plugin,
        "--sha256",
        hashlib.sha256(plugin.read_bytes()).hexdigest(),
        "--requirements",
        root / "plugins.lock",
        "--wheelhouse",
        house,
        "--plugins-dir",
        store,
    )
    cli("enable", "apizr-attest", "--version", "0.0.0", "--plugins-dir", store)
    common = record["common"] | {"trust_store": str(root / "trust")}
    transport = record["transport"] | {
        "authentication": {
            "config_file": str(root / "auth.json"),
            "ca_file": str(root / "ca.crt"),
        }
    }
    discovery = {
        "schema": "apizr.discover-proofs/v1",
        "expected_reference": common["expected_reference"],
        "transport": transport,
    }
    (root / "discover.json").write_text(json.dumps(discovery))
    found = json.loads(
        cli(
            "run",
            "apizr-attest",
            "discover",
            "--arguments",
            root / "discover.json",
            "--plugins-dir",
            store,
        )
    )["result"]
    assert len(found["candidates"]) == 3
    document = common | {
        "schema": "apizr.fetch-proof/v1",
        "artifact_reference": record["publish"]["artifact_reference"],
        "output_dir": str(root / "proof"),
        "transport": transport,
    }
    # Faults are applied to genuine registry responses by the disposable gateway.
    # A failure never makes an export visible; each case is followed by recovery.
    import signal
    import time

    def attempt(data, *, refused=False, discovery=False):
        argument = root / "case.json"
        argument.write_text(json.dumps(data))
        call = [
            str(python),
            "-I",
            "-B",
            "-m",
            "apizr.cli",
            "plugins",
            "run",
            "apizr-attest",
            "discover" if discovery else "fetch",
            "--arguments",
            str(argument),
            "--plugins-dir",
            str(store),
            "--timeout-ms",
            "180000",
        ]
        response = subprocess.run(call, cwd=root, capture_output=True, timeout=185)
        if refused:
            assert response.returncode == 2 and not response.stdout, response.stderr
            assert not (root / "case-proof").exists()
            return {}
        assert response.returncode == 0, response.stderr
        return json.loads(response.stdout)["result"]

    case = document | {"output_dir": str(root / "case-proof")}
    (root / "gateway-mode").write_text("pagination")
    assert len(attempt(discovery, discovery=True)["candidates"]) == 3
    assert (root / "pagination-observed").exists()
    (root / "gateway-mode").write_text("")
    cases = []
    attempt(case | {"artifact_reference": record["invalid_reference"]}, refused=True)
    attempt(case)
    shutil.rmtree(root / "case-proof")
    cases.append("altered-receipt-with-valid-oci-hashes")
    for mode in ("missing-api", "blob-corrupt", "manifest-corrupt"):
        (root / "gateway-mode").write_text(mode)
        attempt(
            discovery if mode == "missing-api" else case,
            refused=True,
            discovery=mode == "missing-api",
        )
        (root / "gateway-mode").write_text("")
        attempt(case)
        shutil.rmtree(root / "case-proof")
        cases.append(mode)
    altered = root / "altered-trust"
    for fault in ("signer", "revoked", "untrusted", "proof-trust"):
        shutil.copytree(root / "trust", altered)
        change = {"trust_store": str(altered)}
        if fault == "signer":
            change["expected_signer"] = "0" * 64
        if fault == "revoked":
            key_id = next(altered.glob("*.pub")).stem
            (altered / "trust.toml").write_text(
                f'version = 1\n[[key]]\nid = "{key_id}"\nname = "revoked"\nstatus = "revoked"\n'
            )
        if fault == "untrusted":
            next(altered.glob("*.pub")).unlink()
        if fault == "proof-trust":
            change["trust_store"] = str(root / "case-proof/trust")
        attempt(case | change, refused=True)
        shutil.rmtree(altered)
        attempt(case)
        shutil.rmtree(root / "case-proof")
        cases.append(fault)
    (root / "gateway-mode").write_text("slow-blob")
    (root / "case.json").write_text(json.dumps(case))
    process = subprocess.Popen(
        [
            str(python),
            "-I",
            "-B",
            "-m",
            "apizr.cli",
            "plugins",
            "run",
            "apizr-attest",
            "fetch",
            "--arguments",
            str(root / "case.json"),
            "--plugins-dir",
            str(store),
            "--timeout-ms",
            "180000",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 30
        while not (root / "blocked-transfer").exists():
            assert time.monotonic() < deadline and process.poll() is None
            time.sleep(0.02)
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=10)
        assert (
            process.returncode == 130
            and not stdout
            and not (root / "case-proof").exists()
        ), stderr
    finally:
        (root / "release-transfer").touch()
        (root / "gateway-mode").write_text("")
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
    attempt(case)
    shutil.rmtree(root / "case-proof")
    (root / "refusals.json").write_text(json.dumps(cases + ["interrupted-transfer"]))
    (root / "fetch.json").write_text(json.dumps(document))
    result = json.loads(
        cli(
            "run",
            "apizr-attest",
            "fetch",
            "--arguments",
            root / "fetch.json",
            "--plugins-dir",
            store,
            "--timeout-ms",
            "360000",
        )
    )["result"]
    assert result["receipt_sha256"] == record["publish"]["receipt_sha256"]
    assert record["hashes"] == {
        n: hashlib.sha256((root / "proof" / n).read_bytes()).hexdigest()
        for n in record["hashes"]
    }
    # The same explicit reader credentials cannot write through the gateway.
    denied = subprocess.run(
        [
            "/opt/oras/oras",
            "attach",
            "--distribution-spec",
            "v1.1-referrers-api",
            "--artifact-type",
            "test/refused",
            common["expected_reference"],
            "proof/receipt.yaml",
            "--registry-config",
            str(root / "auth.json"),
            "--ca-file",
            str(root / "ca.crt"),
        ],
        capture_output=True,
        timeout=30,
    )
    assert denied.returncode != 0
    (root / "verify.json").write_text(
        json.dumps(
            common
            | {"schema": "apizr.verify-delivery/v1", "proof_dir": str(root / "proof")}
        )
    )
    (root / "result.json").write_text(
        json.dumps(
            {
                "fetch": result,
                "refusals": cases + ["interrupted-transfer"],
                "same_six_files": True,
                "read_only_enforced": True,
                "core_unchanged": snapshot(root / "core") == before,
            },
            indent=2,
        )
    )
    assert snapshot(root / "core") == before
    (root / "auth.json").unlink()
    shutil.rmtree(root / "wheels")
    print(
        "PASS discover and verified fetch with read-only registry rights and no Docker socket"
    )


if __name__ == "__main__":
    main()

"""Installed-wheel, real Attest/TSA proof, inside the disposable OCI fixture."""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from threading import Event

from attest_test_authority import authority
from attest_test_authority import command as native_command
from coordinated_distributions import copy_closure
from operator_policy_proof import refuse, write_policy, write_signing_policy
from smoke_oci_plugin import REPO, lock_wheels


def exercise(python, store, work, builds, command, environment):
    house = work / "attest-wheels"
    shutil.copytree(work / "plugin-wheels", house)
    if not copy_closure("attest", house):
        command("uv", "build", "--wheel", REPO / "plugins/attest", "--out-dir", house)
    lock = work / "attest.lock"
    lock_wheels(house, lock)
    base = [str(python), "-I", "-B", "-m", "apizr.cli", "plugins"]
    catalog = work / "catalog-delivery"
    activations = (store / "activations.json").read_bytes()
    command(
        python,
        "-I",
        "-B",
        REPO / "scripts/catalog_plugin_plan.py",
        "--wheelhouse",
        house,
        "--plugin",
        "outerspace-apizr-oci=" + str(work / "plugin.lock"),
        "--plugin",
        "outerspace-apizr-attest=" + str(lock),
        "--commit",
        command(
            "git", "-c", "safe.directory=" + str(REPO), "-C", REPO, "rev-parse", "HEAD"
        ),
        "--output",
        catalog,
        "--profile",
        "delivery",
    )
    plan = catalog / "plan"
    command(
        *base,
        "sync",
        "--project",
        plan / "apizr.toml",
        "--lock",
        plan / "apizr.plugins.lock.json",
        "--wheelhouse",
        house,
        "--plugins-dir",
        store,
        "--json",
    )
    assert (store / "activations.json").read_bytes() == activations
    records = json.loads(command(*base, "list", "--json", "--plugins-dir", store))[
        "installations"
    ]
    assert len({record["environment_id"] for record in records}) == 2
    assert len({len(record["dependencies"]) for record in records}) == 2
    command(
        *base,
        "enable",
        "outerspace-apizr-attest",
        "--version",
        "0.4.2rc2",
        "--plugins-dir",
        store,
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

    operator = work / "operator-signing.json"

    def invoke(operation, arguments, *, refused=False, offline=False, selected=None):
        argsfile = work / f"{operation}-arguments.json"
        argsfile.write_text(json.dumps(arguments))
        args = [
            *base,
            "run",
            "outerspace-apizr-attest",
            operation,
            *(
                ["--operator-policy", str(selected or operator)]
                if operation == "attest"
                else []
            ),
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
        write_signing_policy(python, store, operator, arguments, command)
        publication_only = write_policy(
            python,
            store,
            work / "publication-only.json",
            "outerspace-apizr-attest",
            "publish",
            [arguments["expected_reference"].split("@")[0]],
            command,
        )
        operator_refusals = []
        for selected, code in (
            (None, "operator_policy_required"),
            (publication_only, "operator_operation_denied"),
        ):
            operator_refusals.append(
                refuse(
                    python,
                    store,
                    work,
                    "outerspace-apizr-attest",
                    "attest",
                    arguments,
                    selected,
                    code,
                    environment,
                )
            )
        assert not calls and not output.exists()
        (work / "operator-signing-refusals.json").write_text(
            json.dumps(operator_refusals)
        )
        for name, change in (
            ("wrong-reference", {"expected_reference": pushes[1]["digest_reference"]}),
            ("wrong-signer", {"expected_signer": "0" * 64}),
            ("missing-attest", {"tool": tool | {"executable": "/missing/attest"}}),
            ("wrong-version", {"tool": tool | {"version": "9.0.0"}}),
            ("wrong-hash", {"tool": tool | {"sha256": "0" * 64}}),
        ):
            # Explicitly authorize changed signing identities too: these cases
            # must still exercise native verification, not stop at admission.
            changed_policy = write_signing_policy(
                python,
                store,
                work / "negative-signing.json",
                arguments | change,
                command,
            )
            invoke("attest", arguments | change, refused=True, selected=changed_policy)
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
        if pushes[0].get("proof_requirement") != "required":
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
        for mode in ("timeout", "interruption"):
            received, release = Event(), Event()
            with authority(
                work / (mode + "-tsa"), received=received, release=release
            ) as (
                blocked_url,
                blocked_ca,
                _,
            ):
                shutil.copyfile(blocked_ca, trust / "tsa/blocked.crt")
                blocked = arguments | {
                    "tsa_url": blocked_url,
                    "timeout_ms": 10000 if mode == "timeout" else 300000,
                    "output_dir": str(work / (mode + "-proof")),
                }
                blocked_policy = write_signing_policy(
                    python, store, work / "blocked-signing.json", blocked, command
                )
                blocked_file = work / "blocked-arguments.json"
                blocked_file.write_text(json.dumps(blocked))
                with tempfile.TemporaryDirectory(dir=work) as runtimes:
                    process = subprocess.Popen(
                        [
                            *base,
                            "run",
                            "outerspace-apizr-attest",
                            "attest",
                            "--operator-policy",
                            str(blocked_policy),
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
                        if mode == "interruption":
                            process.send_signal(signal.SIGINT)
                        stdout, stderr = process.communicate(timeout=15)
                        assert (
                            process.returncode == (130 if mode == "interruption" else 2)
                            and not stdout
                        )
                        assert not any(secret in stderr for secret in secrets)
                        assert not list(Path(runtimes).iterdir())
                        assert not (work / (mode + "-proof")).exists()
                        refusals.append(
                            {"case": mode + "-key-cleanup", "refused": True}
                        )
                    finally:
                        release.set()
                        if process.poll() is None:
                            process.kill()
                        process.communicate(timeout=5)
        recovered = arguments | {"output_dir": str(work / "recovered-proof")}
        assert invoke("attest", recovered) is not None
        mcp_build, mcp_push = (
            work / "attest-mcp-build.json",
            work / "attest-mcp-push.json",
        )
        mcp_build.write_text(json.dumps(builds[1]["result"]))
        mcp_push.write_text(json.dumps(pushes[1]))
        mcp_arguments = arguments | {
            "build_result": str(mcp_build),
            "push_result": str(mcp_push),
            "expected_reference": pushes[1]["digest_reference"],
            "output_dir": str(work / "mcp-delivery-proof"),
        }
        mcp_operator = write_signing_policy(
            python, store, work / "operator-mcp-signing.json", mcp_arguments, command
        )
        mcp_signed = invoke("attest", mcp_arguments, selected=mcp_operator)
        assert mcp_signed is not None
        for result, built in (
            (signed, builds[0]["result"]),
            (mcp_signed, builds[1]["result"]),
        ):
            assert (
                result["delivery_manifest_digest"] == built["delivery_manifest_digest"]
            )
            assert (
                result["delivery_plan_digest"]
                == built["delivery_manifest"]["delivery_plan_digest"]
            )
            assert result["attest_tool"] == {k: tool[k] for k in ("version", "sha256")}
        if os.environ.get("APIZR_ARTIFACT_PROOF") == "1":
            from multi_delivery_proof import exercise as multi_delivery

            multi_delivery(
                python, store, work, builds, arguments, command, environment, calls
            )
            from mcp_delivery_proof import install as install_delivery_mcp

            mcp_python = install_delivery_mcp(python, store, work, command)
            multi_delivery(
                python,
                store,
                work,
                builds,
                arguments,
                command,
                environment,
                calls,
                mcp_python=mcp_python,
            )
        key.unlink()  # Publication of an existing proof requires no private key.
        offline = {
            k: arguments[k]
            for k in ("expected_reference", "expected_signer", "trust_store", "tool")
        }
        offline |= {"schema": "apizr.verify-delivery/v1", "proof_dir": str(output)}
        calls_before_verify = len(calls)
        assert invoke("verify", offline, offline=True) == signed
        mcp_offline = offline | {
            "proof_dir": mcp_arguments["output_dir"],
            "expected_reference": mcp_arguments["expected_reference"],
        }
        assert invoke("verify", mcp_offline, offline=True) == mcp_signed
        assert len(calls) == calls_before_verify
        if os.environ.get("APIZR_ARTIFACT_PROOF") == "1":
            from smoke_artifact_publish import exercise

            exercise(
                python,
                store,
                work,
                output,
                work / "recovered-proof",
                arguments,
                command,
                environment,
            )
            from admission_proof import exercise as admit_deliveries

            admit_deliveries(
                python,
                store,
                work,
                builds,
                pushes,
                arguments,
                mcp_arguments,
                command,
                environment,
            )
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
            "rebound-result",
            "delivery-manifest",
            "delivery-plan",
            "build-lineage",
            "push-lineage",
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
            if name in {
                "delivery-manifest",
                "delivery-plan",
                "build-lineage",
                "push-lineage",
            }:
                filename = {
                    "delivery-manifest": "apizr-delivery-manifest.json",
                    "delivery-plan": "build.json",
                    "build-lineage": "build.json",
                    "push-lineage": "push.json",
                }[name]
                path = altered / "delivery" / filename
                value = json.loads(path.read_bytes())
                if name == "delivery-manifest":
                    value["delivery_plan_digest"] = "9" * 64
                elif name == "delivery-plan":
                    value["delivery_plan"]["base_image"] = "python@sha256:" + "9" * 64
                else:
                    value["delivery_manifest_digest"] = "9" * 64
                path.write_text(json.dumps(value))
            if name == "rebound-result":
                # Keep all application hashes internally consistent, but change a
                # signed declaration. Native recomputation must reject it.
                path = altered / "delivery/build.json"
                value = json.loads(path.read_bytes())
                value["tag"] = "other:declaration"
                path.write_text(json.dumps(value))
                path = altered / "delivery/manifest.json"
                value = json.loads(path.read_bytes())
                value["files"]["build.json"] = hashlib.sha256(
                    (altered / "delivery/build.json").read_bytes()
                ).hexdigest()
                path.write_text(
                    json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
                )
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
                    "mcp_signed": mcp_signed,
                    "mcp_verified_offline": mcp_signed,
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

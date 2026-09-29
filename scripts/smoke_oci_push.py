"""Installed-plugin publication proof used only by the disposable registry fixture."""

import base64
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from operator_policy_proof import refuse, write_policy


def exercise(python, store, work, results, command, engine, environment):
    operator = write_policy(
        python,
        store,
        work / "operator-oci.json",
        "outerspace-apizr-oci",
        "push",
        [
            "registry.test:5443/services/rest",
            "registry.test:5443/services/mcp",
            "registry-untrusted.test:5443/services/rest",
        ],
        command,
    )
    operator_refusals = []
    outputs = []
    refusals = []
    secrets = json.loads(Path("/proof/auth/config.json").read_text())["auths"][
        "registry.test:5443"
    ]["auth"]
    tokens = (secrets.encode(), base64.b64decode(secrets).split(b":", 1)[1])

    def invoke(document, *, refused=False, code="plugin_failed"):
        path = work / "push.json"
        path.write_text(json.dumps(document))
        result = subprocess.run(
            [
                str(python),
                "-I",
                "-B",
                "-m",
                "apizr.cli",
                "plugins",
                "run",
                "outerspace-apizr-oci",
                "push",
                "--arguments",
                str(path),
                "--operator-policy",
                str(operator),
                "--plugins-dir",
                str(store),
                "--timeout-ms",
                "360000",
            ],
            cwd=work,
            env=environment,
            capture_output=True,
            timeout=360,
        )
        assert not any(token in result.stdout + result.stderr for token in tokens)
        if refused:
            assert (
                result.returncode == 2
                and result.stdout == b""
                and (
                    result.stderr == b"apizr plugins: plugin_failed\n"
                    if code == "plugin_failed"
                    else json.loads(result.stderr)
                    == {
                        "schema": "apizr.operator-decision/v1",
                        "allowed": False,
                        "code": code,
                    }
                )
            ), (result.returncode, result.stdout, result.stderr)
            return None
        assert result.returncode == 0, (result.stdout, result.stderr)
        reply = json.loads(result.stdout)
        assert reply["status"] == "ok" and reply["result"]["published"] is True
        return reply["result"]

    for index, built in enumerate(results):
        result = built["result"]
        document = {
            "schema": "apizr.oci-push/v1",
            "image_id": result["image_id"],
            "platform": result["platform"],
            "inputs_sha256": result["inputs_sha256"],
            "delivery_manifest": result["delivery_manifest"],
            "delivery_plan": result["delivery_plan"],
            "destination": "registry.test:5443/services/"
            + ("rest" if index == 0 else "mcp")
            + ":v1",
            "docker": {
                "executable": "/usr/local/bin/docker",
                "socket": "/proof/builder.sock",
                "buildx": "/usr/local/libexec/docker/cli-plugins/docker-buildx",
            },
            "authentication": {
                "config_file": "/proof/auth/config.json",
                "ca_file": "/proof/certs/ca.crt",
            },
            "timeout_ms": 300000,
        }
        if index == 0:
            operator_refusals.append(
                refuse(
                    python,
                    store,
                    work,
                    "outerspace-apizr-oci",
                    "push",
                    document,
                    work / "operator-build-rest.json",
                    "operator_operation_denied",
                    environment,
                )
            )
            operator_refusals.append(
                refuse(
                    python,
                    store,
                    work,
                    "outerspace-apizr-oci",
                    "push",
                    document,
                    None,
                    "operator_policy_required",
                    environment,
                )
            )
            operator_refusals.append(
                refuse(
                    python,
                    store,
                    work,
                    "outerspace-apizr-oci",
                    "push",
                    document
                    | {"destination": "registry.test:5443/unauthorized/service:v1"},
                    operator,
                    "operator_repository_denied",
                    environment,
                )
            )
            read_only = work / "operator-read-only.json"
            raw = json.loads(operator.read_bytes())
            for grant in raw["grants"]:
                grant["permissions"] = ["registry.read"]
            read_only.write_text(json.dumps(raw))
            operator_refusals.append(
                refuse(
                    python,
                    store,
                    work,
                    "outerspace-apizr-oci",
                    "push",
                    document,
                    read_only,
                    "operator_permissions_denied",
                    environment,
                )
            )
            (work / "operator-push-refusals.json").write_text(
                json.dumps(operator_refusals)
            )
            bad_auth = work / "bad-auth.json"
            bad_auth.write_text(
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
            for fault in (
                "id",
                "inputs",
                "platform",
                "plan",
                "downgrade",
                "authentication",
                "tls",
            ):
                changed = json.loads(json.dumps(document))
                if fault == "id":
                    changed["image_id"] = "sha256:" + "0" * 64
                if fault == "inputs":
                    changed["inputs_sha256"] = "0" * 64
                if fault == "platform":
                    changed["platform"] = (
                        "linux/arm64"
                        if result["platform"] == "linux/amd64"
                        else "linux/amd64"
                    )
                if fault == "authentication":
                    changed["authentication"]["config_file"] = str(bad_auth)
                if fault == "tls":
                    # The builder daemon trusts registry.test through certs.d.
                    # A second DNS alias has the same valid SAN but no implicit
                    # client CA installation, proving an untrusted-chain refusal.
                    tls_dir = work / "untrusted-auth"
                    tls_dir.mkdir()
                    tls_auth = tls_dir / "config.json"
                    tls_auth.write_text(
                        json.dumps(
                            {
                                "auths": {
                                    "registry-untrusted.test:5443": {"auth": secrets}
                                }
                            }
                        )
                    )
                    changed["destination"] = changed["destination"].replace(
                        "registry.test", "registry-untrusted.test"
                    )
                    changed["authentication"] = {"config_file": str(tls_auth)}
                    check = subprocess.run(
                        [
                            "/usr/local/bin/docker",
                            "--config",
                            str(tls_dir),
                            "manifest",
                            "inspect",
                            changed["destination"],
                        ],
                        env={"PATH": os.defpath},
                        capture_output=True,
                        timeout=15,
                    )
                    assert check.returncode != 0 and b"x509:" in check.stderr

                if fault in {"id", "inputs", "platform"}:
                    # Identity/input faults reach independent local-image checks.
                    # Platform substitution also violates the immutable plan and
                    # is refused earlier by the shared request validator.
                    field = {
                        "id": "image_id",
                        "inputs": "inputs_sha256",
                        "platform": "platform",
                    }[fault]
                    changed["delivery_manifest"][field] = changed[field]
                if fault == "plan":
                    changed["delivery_manifest"]["delivery_plan_digest"]["value"] = (
                        "0" * 64
                    )
                if fault == "downgrade":
                    changed.pop("delivery_manifest")
                invoke(
                    changed,
                    refused=True,
                    code="operator_arguments_invalid"
                    if fault in {"platform", "plan", "downgrade"}
                    else "plugin_failed",
                )
                refusals.append({"case": fault, "refused": True})
            interrupt(python, store, work, document, environment, operator)
            # The build tag can move; publication still selects the recorded ID.
            other = json.loads(engine("image", "inspect", "python:3.14-slim"))[0]["Id"]
            engine("image", "tag", other, result["tag"])
        published = invoke(document)
        assert published is not None
        assert invoke(document) == published
        outputs.append(published)
        required = result["delivery_plan"].get("proof_requirement") == "required"
        if required:
            assert published["transfer_verified"] is True
            assert published["destination_promoted"] is False
            assert published["delivery_admitted"] is False
            absent = subprocess.run(
                [
                    "/usr/local/bin/docker",
                    "--config",
                    "/proof/auth",
                    "manifest",
                    "inspect",
                    document["destination"],
                ],
                capture_output=True,
                timeout=15,
            )
            assert absent.returncode != 0 and b"no such manifest:" in absent.stderr

        if index == 0:
            # Complete the real upload/promotion, then corrupt only the client's
            # verification response. The remote image remains; a normal repeat
            # must verify it and recover without claiming rollback.
            marker = work / "promoted"
            wrapper = work / "verification-observer"
            wrapper.write_text(
                f"#!{sys.executable}\n"
                + f"""import os,subprocess,sys
from pathlib import Path

args=sys.argv[1:]
marker=Path({str(marker)!r})
if args[:{2 if required else 3}] == {["image", "push"] if required else ["buildx", "imagetools", "create"]!r}:
 result=subprocess.run(['/usr/local/bin/docker',*args])
 if result.returncode == 0: marker.write_text('promoted')
 raise SystemExit(result.returncode)
if args[:2] == ['manifest','inspect'] and marker.exists():
 print('{{}}')
 raise SystemExit(0)
os.execv('/usr/local/bin/docker',['/usr/local/bin/docker',*args])
"""
            )
            wrapper.chmod(0o700)
            verification = document | {
                "destination": document["destination"] + "-verification"
            }
            invoke(
                verification
                | {"docker": document["docker"] | {"executable": str(wrapper)}},
                refused=True,
            )
            assert marker.exists()
            assert invoke(verification) is not None
            refusals.append(
                {
                    "case": "post-publication-verification",
                    "refused": True,
                    "remote_recovered": True,
                }
            )
        if index == 1:
            # Same destination as REST, but a different MCP image: never overwrite.
            conflict = outputs[0]["destination"]
            if required:
                conflict += "-conflict"
                # Fixture-only competing writer, through the TLS-configured daemon.
                command(
                    "/usr/local/bin/docker",
                    "--host",
                    "unix:///proof/builder.sock",
                    "image",
                    "tag",
                    results[0]["result"]["image_id"],
                    conflict,
                )
                command(
                    "/usr/local/bin/docker",
                    "--config",
                    "/proof/auth",
                    "--host",
                    "unix:///proof/builder.sock",
                    "image",
                    "push",
                    "--platform",
                    results[0]["result"]["platform"],
                    conflict,
                )
            invoke(document | {"destination": conflict}, refused=True)
            refusals.append({"case": "tag-conflict", "refused": True})
        command(
            "/usr/local/bin/docker",
            "--config",
            "/proof/auth",
            "--host",
            "unix:///proof/consumer.sock",
            "pull",
            published["digest_reference"],
        )
        info = json.loads(
            command(
                "/usr/local/bin/docker",
                "--host",
                "unix:///proof/consumer.sock",
                "image",
                "inspect",
                published["digest_reference"],
            )
        )[0]
        assert (
            info["Config"]["Labels"]["sh.outerspace.apizr.inputs-sha256"]
            == result["inputs_sha256"]
        )
        assert info["Os"] + "/" + info["Architecture"] == result["platform"]
    (work / "push-results.json").write_text(json.dumps(outputs, indent=2))
    (work / "push-refusals.json").write_text(json.dumps(refusals, indent=2))
    return [item["digest_reference"] for item in outputs]


def interrupt(python, store, work, document, environment, operator):
    """Interrupt after the upload client starts; never infer daemon/registry rollback."""
    marker = work / "push-started.json"
    wrapper = work / "push-observer"
    wrapper.write_text(
        f"#!{sys.executable}\n"
        + f"""import json,os,signal,subprocess,sys
from pathlib import Path

args=sys.argv[1:]
if args[:2] != ['image','push']:
 os.execv('/usr/local/bin/docker',['/usr/local/bin/docker',*args])
child=subprocess.Popen(['/usr/local/bin/docker',*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
assert child.stdout is not None
line=child.stdout.readline(65536)
if not line: raise SystemExit(3)
Path({str(marker)!r}).write_text(json.dumps({{'cwd':os.getcwd(),'client':child.pid}}))
signal.pause()
"""
    )
    wrapper.chmod(0o700)
    path = work / "interrupt-push.json"
    path.write_text(
        json.dumps(
            document
            | {
                "destination": document["destination"] + "-interrupted",
                "docker": document["docker"] | {"executable": str(wrapper)},
            }
        )
    )
    child = subprocess.Popen(
        [
            str(python),
            "-I",
            "-B",
            "-m",
            "apizr.cli",
            "plugins",
            "run",
            "outerspace-apizr-oci",
            "push",
            "--arguments",
            str(path),
            "--operator-policy",
            str(operator),
            "--plugins-dir",
            str(store),
            "--timeout-ms",
            "360000",
        ],
        cwd=work,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 45
        while not marker.exists():
            if child.poll() is not None or time.monotonic() > deadline:
                raise AssertionError(
                    "upload handshake absent: " + str(child.communicate(timeout=5))
                )
            time.sleep(0.02)
        state = json.loads(marker.read_text())
        child.send_signal(signal.SIGINT)
        out, err = child.communicate(timeout=5)
        assert (
            child.returncode == 130
            and out == b""
            and err == b"apizr plugins: cancelled\n"
        )
        assert not Path(state["cwd"]).exists()
        (work / "push-interruption.json").write_text(
            json.dumps(
                {
                    "exit_code": 130,
                    "context_removed": True,
                    "remote_state": "unconfirmed",
                }
            )
        )
    finally:
        if child.poll() is None:
            child.send_signal(signal.SIGINT)
        child.communicate(timeout=5)

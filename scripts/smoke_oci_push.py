"""Installed-plugin publication proof used only by the disposable registry fixture."""

import base64
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def exercise(python, store, work, results, command, engine, environment):
    outputs = []
    refusals = []
    secrets = json.loads(Path("/proof/auth/config.json").read_text())["auths"][
        "registry.test:5443"
    ]["auth"]
    tokens = (secrets.encode(), base64.b64decode(secrets).split(b":", 1)[1])

    def invoke(document, *, refused=False):
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
                "apizr-oci",
                "push",
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
            timeout=360,
        )
        assert not any(token in result.stdout + result.stderr for token in tokens)
        if refused:
            assert (
                result.returncode == 2
                and result.stdout == b""
                and result.stderr == b"apizr plugins: plugin_failed\n"
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
            for fault in ("id", "inputs", "platform", "authentication", "tls"):
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

                invoke(changed, refused=True)
                refusals.append({"case": fault, "refused": True})
            interrupt(python, store, work, document, environment)
            # The build tag can move; publication still selects the recorded ID.
            other = json.loads(engine("image", "inspect", "python:3.14-slim"))[0]["Id"]
            engine("image", "tag", other, result["tag"])
        published = invoke(document)
        assert published is not None
        assert invoke(document) == published
        outputs.append(published)
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
if args[:3] == ['buildx','imagetools','create']:
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
            invoke(document | {"destination": outputs[0]["destination"]}, refused=True)
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


def interrupt(python, store, work, document, environment):
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
            "apizr-oci",
            "push",
            "--arguments",
            str(path),
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

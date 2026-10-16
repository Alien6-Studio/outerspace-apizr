"""Qualify the real workspace extension host over temporary loopback SSH."""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from scripts.qualification.interfaces.vscode_proof import ROOT, command


def dockerfile(base: str, wheel: str) -> str:
    return f"""FROM {base}
RUN apt-get update && apt-get install --no-install-recommends -y openssh-server ca-certificates curl xz-utils git && rm -rf /var/lib/apt/lists/*
RUN useradd --uid {os.getuid()} --create-home --shell /bin/bash apizr && mkdir -p /run/sshd && echo 'apizr:disabled-qualification-password' | chpasswd
COPY engine.lock /opt/engine.lock
COPY {wheel} /opt/
RUN python -m pip install --only-binary=:all: uv==0.13.1 && uv venv /opt/apizr && uv pip install --python /opt/apizr/bin/python --require-hashes --only-binary :all: -r /opt/engine.lock && uv pip install --python /opt/apizr/bin/python --no-deps --no-index /opt/{wheel}
COPY authorized_keys /etc/apizr-authorized_keys
RUN printf '%s\\n' 'PasswordAuthentication no' 'KbdInteractiveAuthentication no' 'PubkeyAuthentication yes' 'AuthorizedKeysFile /etc/apizr-authorized_keys' 'PermitRootLogin no' 'AllowUsers apizr' 'AllowTcpForwarding yes' 'X11Forwarding no' > /etc/ssh/sshd_config.d/apizr.conf
CMD ["/usr/sbin/sshd", "-D", "-e"]
"""


def setup(root: Path) -> str:
    """The separate workspace test driver never ships with the product VSIX."""
    driver = (
        "const vscode=require('vscode'); exports.activate=async()=>{"
        f"process.env.APIZR_VSCODE_PROOF={json.dumps(str(root / 'proof'))};"
        "process.env.APIZR_VSCODE_UNTRUSTED='0';try {"
        "if(vscode.env.remoteName!=='ssh-remote')throw new Error('Expected actual remote SSH extension host');"
        "await require('/workspace/editors/vscode/test/host.cjs').run();"
        "}catch(e){require('fs').writeFileSync("
        + json.dumps(str(root / "proof/driver-error.json"))
        + ",JSON.stringify({message:String(e)}));}};"
    )
    return f"""import json,zipfile
from pathlib import Path
root=Path({str(root)!r})
extensions=Path.home()/'.vscode-server/extensions'
extensions.mkdir(parents=True,exist_ok=True)
target=extensions/'alien6-studio.apizr-0.4.6'
with zipfile.ZipFile(root/'apizr.vsix') as archive:
    for name in archive.namelist():
        if name.startswith('extension/'):
            path=target/name.removeprefix('extension/')
            assert path.is_relative_to(target) and '..' not in Path(name).parts
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(archive.read(name))
driver=extensions/'apizr-qualification.remote-driver-1.0.0'
driver.mkdir()
(driver/'package.json').write_text(json.dumps(dict(name='remote-driver',publisher='apizr-qualification',version='1.0.0',engines={{'vscode':'^1.140.0'}},main='./index.cjs',activationEvents=['onStartupFinished'],extensionKind=['workspace'])))
(driver/'index.cjs').write_text({driver!r})
"""


def prove(args: argparse.Namespace) -> dict:
    dirty = bool(command(["git", "status", "--porcelain"], cwd=ROOT).strip())
    if dirty and not args.allow_dirty:
        raise ValueError("Retained remote qualification requires a clean checkout")
    root = args.output.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    context = root / "context"
    context.mkdir()
    wheel = args.wheel.resolve()
    name = wheel.name
    if not re.fullmatch(r"outerspace_apizr-[A-Za-z0-9_.+]+-py3-none-any\.whl", name):
        raise ValueError("Select a coordinated pure-Python core wheel")
    shutil.copyfile(wheel, context / name)
    shutil.copyfile(args.requirements, context / "engine.lock")
    shutil.copyfile(args.vsix, root / "apizr.vsix")
    policy = json.loads((ROOT / "policy/vscode-distribution.json").read_text())
    remote = policy["remote_ssh"]
    image = "apizr-vscode-ssh-qualification:" + uuid4().hex
    image_built = False
    container: str | None = None
    desktop: subprocess.Popen | None = None
    profile, extensions = root / "profile", root / "extensions"
    (profile / "User").mkdir(parents=True)
    extensions.mkdir()
    code = args.code.resolve()
    try:
        command(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", root / "identity"],
            cwd=root,
        )
        shutil.copyfile(root / "identity.pub", context / "authorized_keys")
        (context / "Dockerfile").write_text(dockerfile(remote["container_base"], name))
        (root / "build.log").write_text(
            command(["docker", "build", "--tag", image, context], cwd=root, timeout=600)
        )
        image_built = True
        container = command(
            [
                "docker",
                "run",
                "--detach",
                "--publish",
                "127.0.0.1::22",
                "--mount",
                f"type=bind,source={root},target={root}",
                "--mount",
                f"type=bind,source={ROOT},target=/workspace,readonly",
                image,
            ],
            cwd=root,
        ).strip()
        info = json.loads(command(["docker", "inspect", container], cwd=root))[0]
        port = info["NetworkSettings"]["Ports"]["22/tcp"][0]["HostPort"]
        (root / "ssh-config").write_text(
            f"Host apizr-qualification\n  HostName 127.0.0.1\n  Port {port}\n  User apizr\n"
            f"  IdentityFile {root}/identity\n  IdentitiesOnly yes\n  BatchMode yes\n"
            f"  StrictHostKeyChecking accept-new\n  UserKnownHostsFile {root}/known_hosts\n"
        )
        (root / "proof").mkdir()
        base = [
            "docker",
            "exec",
            "--user",
            str(os.getuid()),
            "--workdir",
            "/workspace",
            "--env",
            "APIZR_TELEMETRY=0",
            container,
            "/opt/apizr/bin/python",
        ]
        (root / "prepare.log").write_text(
            command(
                [
                    *base,
                    "-c",
                    f"from pathlib import Path;from scripts.qualification.interfaces.vscode_proof import prepare;prepare(Path({str(root / 'proof')!r}),Path('/opt/apizr/bin/python'))",
                ],
                cwd=root,
            )
        )
        (root / "remote-setup.py").write_text(setup(root))
        command([*base, root / "remote-setup.py"], cwd=root)
        platform = json.loads(
            command(
                [
                    *base,
                    "-c",
                    "import json,platform;print(json.dumps(dict(os=platform.system(),architecture=platform.machine(),python=platform.python_version(),libc=platform.libc_ver())))",
                ],
                cwd=root,
            )
        )
        settings = {
            "update.mode": "none",
            "extensions.autoUpdate": False,
            "extensions.autoCheckUpdates": False,
            "telemetry.telemetryLevel": "off",
            "workbench.startupEditor": "none",
            "security.workspace.trust.enabled": False,
            "remote.SSH.configFile": str(root / "ssh-config"),
            "remote.SSH.remotePlatform": {"apizr-qualification": "linux"},
            "remote.SSH.useExecServer": False,
            "remote.SSH.useLocalServer": False,
            "apizr.engine.mode": "python",
            "apizr.engine.python": "/opt/apizr/bin/python",
            "apizr.workspace.project": str(root / "proof/project/apizr.toml"),
            "apizr.operatorPolicy": str(root / "proof/operator.json"),
            "apizr.telemetry.enabled": False,
        }
        (profile / "User/settings.json").write_text(json.dumps(settings))
        common = [code, "--user-data-dir", profile, "--extensions-dir", extensions]
        (root / "install.log").write_text(
            command(
                [
                    *common,
                    "--install-extension",
                    remote["extension"] + "@" + remote["version"],
                ],
                cwd=root,
            )
        )
        versions = command(
            [*common, "--list-extensions", "--show-versions"], cwd=root
        ).splitlines()
        assert remote["extension"] + "@" + remote["version"] in versions
        host = code.parent.parent / "code"
        if len(code.parents) > 3 and (code.parents[3] / "MacOS/Code").is_file():
            host = code.parents[3] / "MacOS/Code"
        arguments = [
            host,
            *common[1:],
            "--remote",
            "ssh-remote+apizr-qualification",
            "--folder-uri",
            "vscode-remote://ssh-remote+apizr-qualification"
            + str(root / "proof/project"),
            "--new-window",
            "--skip-welcome",
            "--disable-updates",
            "--disable-telemetry",
        ]
        if os.uname().sysname == "Linux":
            arguments.extend(("--no-sandbox", "--disable-gpu"))
        env = dict(os.environ)
        env.pop("ELECTRON_RUN_AS_NODE", None)
        env.pop("VSCODE_IPC_HOOK_CLI", None)
        with (root / "desktop.log").open("w") as log:
            desktop = subprocess.Popen(
                list(map(str, arguments)),
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            deadline = time.monotonic() + 240
            proof_path = root / "proof/proof.json"
            while not proof_path.exists() and time.monotonic() < deadline:
                if (root / "proof/driver-error.json").exists():
                    raise ValueError("Remote workspace test driver failed")
                time.sleep(0.25)
            proof = json.loads(proof_path.read_text())
        assert (
            proof["result"] == "pass"
            and proof["remote"] == "ssh-remote"
            and proof["outside_checkout"]
        )
        result = {
            "schema_version": "apizr.vscode-ssh-proof/v1",
            "result": "pass",
            "source_commit": command(["git", "rev-parse", "HEAD"], cwd=ROOT).strip(),
            "source_dirty": dirty,
            "qualifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "vsix_sha256": hashlib.sha256(args.vsix.read_bytes()).hexdigest(),
            "requirements_sha256": hashlib.sha256(
                args.requirements.read_bytes()
            ).hexdigest(),
            "container_base": remote["container_base"],
            "container_image": info["Image"],
            "remote_extensions": sorted(versions),
            "remote_platform": platform,
            "proof": proof,
        }
    finally:
        (root / "identity").unlink(missing_ok=True)
        try:
            if desktop is not None and desktop.poll() is None:
                os.killpg(desktop.pid, signal.SIGTERM)
                try:
                    desktop.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(desktop.pid, signal.SIGKILL)
                    desktop.wait(timeout=5)
        finally:
            try:
                if container is not None:
                    subprocess.run(
                        ["docker", "rm", "--force", container],
                        capture_output=True,
                        check=True,
                        timeout=60,
                    )
            finally:
                if image_built:
                    subprocess.run(
                        ["docker", "image", "rm", image],
                        capture_output=True,
                        check=True,
                        timeout=60,
                    )
    result["cleanup_completed"] = True
    (root / "remote-proof.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--vsix", type=Path, required=True)
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Local development proof only; recorded explicitly",
    )
    args = parser.parse_args()
    if os.getuid() == 0 or any(c.isspace() for c in str(args.output.resolve())):
        parser.error(
            "Use an unprivileged host account and an output path without whitespace"
        )
    print(json.dumps(prove(args)))


if __name__ == "__main__":
    main()

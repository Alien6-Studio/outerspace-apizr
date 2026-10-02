"""Composite Action adapter: install a verified core, then call its public CLI."""

import email.parser
import hashlib
import io
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:rc[1-9][0-9]*)?")
OUTPUT = re.compile(r"[A-Za-z0-9_.-]{1,64}(?:/[A-Za-z0-9_.-]{1,64}){0,3}")
MAX_WHEEL = 32 * 1024 * 1024
TOKENS = ("GITHUB_TOKEN", "GH_TOKEN", "CI_JOB_TOKEN", "GITLAB_TOKEN")


class Refused(ValueError):
    """Only fixed diagnostics may cross the adapter boundary."""


def invocation(values):
    operation = values["operation"]
    if operation not in ("check", "build-rest", "build-mcp"):
        raise Refused("forge_operation_invalid")
    if values["authorize-analysis"] not in ("true", "false"):
        raise Refused("forge_authority_invalid")
    authorized = values["authorize-analysis"] == "true"
    policy = values["operator-policy"]
    if bool(policy) == authorized:
        raise Refused("forge_authority_required")
    if not VERSION.fullmatch(values["apizr-version"]):
        raise Refused("forge_version_invalid")
    output = values["output-dir"]
    if not OUTPUT.fullmatch(output) or any(p in (".", "..") for p in output.split("/")):
        raise Refused("forge_output_invalid")
    for key in ("project", "operator-policy"):
        value = values[key]
        if len(value) > 4096 or "\0" in value:
            raise Refused("forge_path_invalid")
    argv = ["ci", operation, "--project", values["project"], "--output-dir", output]
    argv += (
        ["--authorize-project-analysis"]
        if authorized
        else ["--operator-policy", policy]
    )
    return argv


def wheel_bytes(path, expected_hash, version):
    """Read one bounded regular local wheel without following any symlink."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise Refused("forge_wheel_hash_invalid")
    source = Path(path)
    if "://" in path or ".." in source.parts or not source.name.endswith(".whl"):
        raise Refused("forge_wheel_path_invalid")
    source = Path(os.path.abspath(source))
    # macOS system aliases are not user-controlled output/source links.
    for alias in ("/var", "/tmp"):
        if source.is_relative_to(alias) and Path(alias).is_symlink():
            source = Path(alias).resolve() / source.relative_to(alias)
    descriptor = os.open(source.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in source.parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        fd = os.open(
            source.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor
        )
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise Refused("forge_wheel_path_invalid")
            raw = stream.read(MAX_WHEEL + 1)
    finally:
        os.close(descriptor)
    if len(raw) > MAX_WHEEL or hashlib.sha256(raw).hexdigest() != expected_hash:
        raise Refused("forge_wheel_hash_mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        metadata = [
            i for i in archive.infolist() if i.filename.endswith(".dist-info/METADATA")
        ]
        if len(metadata) != 1 or metadata[0].file_size > 65536:
            raise Refused("forge_wheel_metadata_invalid")
        message = email.parser.BytesParser().parsebytes(archive.read(metadata[0]))
        if message.get_all("Name") != ["outerspace-apizr"] or message.get_all(
            "Version"
        ) != [version]:
            raise Refused("forge_wheel_identity_mismatch")
    if version != "0.4.3":
        raise Refused("forge_wheel_development_version_required")
    return source.name, raw


def child(command, environment, *, quiet=False):
    """Forward job cancellation to the single foreground child; never retry."""
    process = subprocess.Popen(
        command,
        env=environment,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.DEVNULL if quiet else None,
    )
    previous = {}

    def forward(number, frame):
        process.send_signal(number)

    for number in (signal.SIGINT, signal.SIGTERM):
        previous[number] = signal.signal(number, forward)
    try:
        status = process.wait()
        return 128 - status if status < 0 else status
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def main():
    try:
        values = {
            key: os.environ.get("APIZR_" + key.upper().replace("-", "_"), "")
            for key in (
                "operation",
                "project",
                "authorize-analysis",
                "operator-policy",
                "output-dir",
                "apizr-version",
                "wheel-path",
                "wheel-sha256",
            )
        }
        argv = invocation(values)
        if not (3, 11) <= sys.version_info[:2] <= (3, 14):
            raise Refused("forge_python_unsupported")
        workspace = Path(os.environ["GITHUB_WORKSPACE"])
        if not workspace.is_dir() or Path.cwd().resolve() != workspace.resolve():
            raise Refused("forge_workspace_missing")
        if not Path(values["project"]).is_file():
            raise Refused("forge_project_missing_checkout_required")
        wheel, digest = values["wheel-path"], values["wheel-sha256"]
        if bool(wheel) != bool(digest):
            raise Refused("forge_wheel_pair_required")
        selected = (
            wheel_bytes(wheel, digest, values["apizr-version"]) if wheel else None
        )
        with tempfile.TemporaryDirectory(
            prefix="apizr-action-", dir=os.environ["RUNNER_TEMP"]
        ) as directory:
            temporary = Path(directory)
            environment = {
                key: os.environ[key]
                for key in ("PATH", "SYSTEMROOT", "LANG", "TMPDIR")
                if key in os.environ
            }
            environment.update(
                HOME=str(temporary),
                PIP_CONFIG_FILE=os.devnull,
                PYTHONDONTWRITEBYTECODE="1",
            )
            target = temporary / "venv"
            venv.EnvBuilder(with_pip=True).create(target)
            python = str(target / "bin/python")
            package = "outerspace-apizr==" + values["apizr-version"]
            if selected:
                snapshot = temporary / selected[0]
                snapshot.write_bytes(selected[1])
                package = str(snapshot)
            status = child(
                [
                    python,
                    "-I",
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--index-url",
                    "https://pypi.org/simple",
                    package,
                ],
                environment,
                quiet=True,
            )
            if status in (130, 143):
                return status
            if status:
                raise Refused("forge_install_failed")
            cli = str(target / "bin/apizr")
            installed = subprocess.run(
                [cli, "--version"], env=environment, capture_output=True, check=False
            )
            if (
                installed.returncode
                or installed.stdout.decode().strip()
                != "outerspace-apizr " + values["apizr-version"]
            ):
                raise Refused("forge_installed_version_mismatch")
            status = child([cli, *argv], environment)
            result = Path(values["output-dir"]) / "result.json"
            # Never read/emit a pre-existing result after an invocation conflict.
            if status in (0, 1) and result.is_file() and not result.is_symlink():
                raw = result.read_bytes()
                if len(raw) > 1024 * 1024:
                    raise Refused("forge_result_invalid")
                state = json.loads(raw)["state"]
                if state not in ("success", "refused"):
                    raise Refused("forge_result_invalid")
                with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                    stream.write(
                        f"result={result.as_posix()}\nartifacts={values['output-dir']}\napizr-version={values['apizr-version']}\nstate={state}\n"
                    )
            return status
    except Refused as error:
        print(str(error), file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError, zipfile.BadZipFile):
        print("forge_configuration_invalid", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

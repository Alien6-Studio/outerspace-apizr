"""Disposable OpenSSH server/agent fixture; never uses the user's keys/service."""

import contextlib
import os
import pwd
import shutil
import signal
import socket
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from git_https_fixture import repository


@dataclass(frozen=True)
class SSHFixture:
    url: str
    source: Path
    commit: str
    socket: Path
    known_hosts: Path
    root: Path


def run(*arguments: str) -> str:
    return subprocess.check_output(
        arguments, stderr=subprocess.PIPE, text=True, timeout=10
    ).strip()


def key(path: Path) -> None:
    run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path))


def stop(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def wait_socket(path: Path, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 5
    while not path.exists():
        if process.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError("test SSH agent did not start")
        time.sleep(0.01)


@contextlib.contextmanager
def agent(root: Path, identity: Path | None) -> Iterator[Path]:
    # Unix sockets have short platform limits, independent of pytest's long paths.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="az-agent-", dir="/tmp") as directory:
        path = Path(directory) / "agent"
        with (root / "agent.log").open("wb") as log:
            process = subprocess.Popen(
                ["ssh-agent", "-D", "-a", str(path)],
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            try:
                wait_socket(path, process)
                if identity is not None:
                    subprocess.run(
                        ["ssh-add", str(identity)],
                        env={"PATH": os.defpath, "SSH_AUTH_SOCK": str(path)},
                        check=True,
                        capture_output=True,
                        timeout=5,
                    )
                yield path
            finally:
                stop(process)


@contextlib.contextmanager
def server(root: Path) -> Iterator[SSHFixture]:
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    source, commit = repository(root)
    for name in ("host", "identity"):
        key(root / name)
    (root / "authorized_keys").write_bytes((root / "identity.pub").read_bytes())
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    user = pwd.getpwuid(os.getuid()).pw_name
    config = root / "sshd_config"
    config.write_text(
        f"Port {port}\nListenAddress 127.0.0.1\nHostKey {root}/host\n"
        f"PidFile {root}/sshd.pid\nAuthorizedKeysFile {root}/authorized_keys\n"
        f"AllowUsers {user}\nStrictModes no\nUsePAM no\n"
        "PasswordAuthentication no\nKbdInteractiveAuthentication no\n"
        "PubkeyAuthentication yes\nPermitRootLogin prohibit-password\n"
        "AllowAgentForwarding no\nAllowTcpForwarding no\nX11Forwarding no\n"
        "PermitTunnel no\nPermitUserEnvironment no\nPermitUserRC no\n"
        "LogLevel VERBOSE\n"
    )
    executable = shutil.which("sshd") or "/usr/sbin/sshd"
    with (root / "sshd.log").open("wb") as log:
        process = subprocess.Popen(
            [executable, "-D", "-e", "-f", str(config)],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError((root / "sshd.log").read_text()) from None
                    time.sleep(0.01)
            known = root / "known_hosts"
            known.write_text(f"[127.0.0.1]:{port} " + (root / "host.pub").read_text())
            with agent(root, root / "identity") as path:
                yield SSHFixture(
                    f"ssh://{user}@127.0.0.1:{port}{source}",
                    source,
                    commit,
                    path,
                    known,
                    root,
                )
        finally:
            stop(process)

"""Explicit agent-only OpenSSH transport, without inherited client configuration."""

import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit

from .models import GitSourceError

MAX_KNOWN_HOSTS_BYTES = 4 * 1024 * 1024
_USER = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"
_HOST = r"(?:[A-Za-z0-9][A-Za-z0-9.-]*|\[[0-9A-Fa-f:]+\])"
_PATH = r"/?[A-Za-z0-9_.][A-Za-z0-9_./-]*"
_SCP = re.compile(rf"({_USER})@({_HOST}):({_PATH})\Z")


def is_ssh(repository: str) -> bool:
    return repository.startswith("ssh://") or _SCP.fullmatch(repository) is not None


def validate_ssh_url(repository: str) -> None:
    try:
        if len(repository) > 4096 or any(
            ord(c) <= 32 or ord(c) >= 127 for c in repository
        ):
            raise ValueError
        if repository.startswith("ssh://"):
            parsed = urlsplit(repository)
            # Require an explicit user; never fall back to the local login name.
            if (
                parsed.scheme != "ssh"
                or parsed.username is None
                or not re.fullmatch(_USER, parsed.username)
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or not re.fullmatch(rf"{_USER}@{_HOST}(?::[0-9]+)?", parsed.netloc)
                or not re.fullmatch(_PATH, parsed.path)
                or parsed.port is not None
                and not 1 <= parsed.port <= 65535
            ):
                raise ValueError
            path = parsed.path
        else:
            match = _SCP.fullmatch(repository)
            if match is None:
                raise ValueError
            path = match[3]
        if any(part in (".", "..", "") for part in path.lstrip("/").split("/")):
            raise ValueError
    except (ValueError, UnicodeError):
        raise GitSourceError("git_invalid_url") from None


def configure_ssh(work: Path, agent_socket: Path, known_hosts: Path) -> dict[str, str]:
    """Return additions to Git's isolated environment; no key is read or copied."""
    executable = shutil.which("ssh")
    if executable is None:
        raise GitSourceError("git_ssh_not_found")
    try:
        agent = agent_socket.resolve(strict=True)
        if not stat.S_ISSOCK(agent.stat().st_mode):
            raise OSError
    except (OSError, RuntimeError):
        # Path.resolve raises RuntimeError for symlink loops on Python 3.11.
        raise GitSourceError("git_ssh_agent_unavailable") from None
    try:
        # Reject special files before reading; O_NONBLOCK also bounds a FIFO race.
        fd = os.open(known_hosts, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise OSError
            contents = stream.read(MAX_KNOWN_HOSTS_BYTES + 1)
            if len(contents) > MAX_KNOWN_HOSTS_BYTES:
                raise GitSourceError("git_ssh_known_hosts_limit")
    except OSError:
        raise GitSourceError("git_ssh_known_hosts_unavailable") from None
    # Fixed relative filename avoids OpenSSH token/environment expansion of
    # user-supplied paths. Git and its SSH child run in this private directory.
    (work / "ssh-known-hosts").write_bytes(contents)
    command = [str(Path(executable).absolute()), "-F", os.devnull, "-T"]
    for setting in (
        "BatchMode=yes",
        "PreferredAuthentications=publickey",
        "PasswordAuthentication=no",
        "KbdInteractiveAuthentication=no",
        "GSSAPIAuthentication=no",
        "HostbasedAuthentication=no",
        "IdentityFile=none",
        "CertificateFile=none",
        "IdentityAgent=SSH_AUTH_SOCK",
        "IdentitiesOnly=no",
        "PKCS11Provider=none",
        "SecurityKeyProvider=none",
        "AddKeysToAgent=no",
        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=./ssh-known-hosts",
        "GlobalKnownHostsFile=/dev/null",
        "KnownHostsCommand=none",
        "UpdateHostKeys=no",
        "VerifyHostKeyDNS=no",
        "CheckHostIP=no",
        "ProxyCommand=none",
        "ProxyJump=none",
        "PermitLocalCommand=no",
        "ClearAllForwardings=yes",
        "ForwardAgent=no",
        "ForwardX11=no",
        "Tunnel=no",
        "ControlMaster=no",
        "ControlPath=none",
        "ControlPersist=no",
        "CanonicalizeHostname=no",
        "ConnectionAttempts=1",
        "ConnectTimeout=10",
        "ServerAliveInterval=5",
        "ServerAliveCountMax=1",
        "SendEnv=-*",
        "LogLevel=ERROR",
    ):
        command.extend(("-o", setting))
    (work / "ssh-argv.json").write_text(json.dumps(command))
    helper = work / "ssh-exec.py"
    helper.write_text(
        "import json, os, sys\n"
        "with open('ssh-argv.json') as stream: command = json.load(stream)\n"
        "os.execv(command[0], [*command, *sys.argv[1:]])\n"
    )
    launcher = work / "ssh-launcher"
    # Constant shell text, no command construction from paths, URLs or options.
    # Quoted argv forwarding supports Python installations with spaces as well.
    launcher.write_text(
        '#!/bin/sh\nexec "$APIZR_SSH_PYTHON" -I -S "$APIZR_SSH_HELPER" "$@"\n'
    )
    launcher.chmod(0o700)
    return {
        "GIT_SSH": str(launcher),
        "GIT_SSH_VARIANT": "ssh",
        "GIT_ALLOW_PROTOCOL": "ssh",
        "SSH_AUTH_SOCK": str(agent),
        "SSH_ASKPASS_REQUIRE": "never",
        "APIZR_SSH_PYTHON": sys.executable,
        "APIZR_SSH_HELPER": str(helper),
    }

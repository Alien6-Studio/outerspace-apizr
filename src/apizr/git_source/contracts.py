"""Pure Git source validation shared by acquisition and operator grants."""

import re
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import model_validator

from apizr.contracts.publication import Model

from .models import GitSourceError

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


def validate_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        if (
            len(url) > 4096
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
            or "\\" in unquote(url)
            or any(ord(c) <= 32 or ord(c) == 127 for c in unquote(url))
        ):
            raise ValueError
        _ = parsed.port
    except (ValueError, UnicodeError):
        raise GitSourceError("git_invalid_url") from None


def validate_ref(reference: str) -> None:
    if (
        not reference
        or len(reference) > 1024
        or reference.startswith("-")
        or ".." in reference
        or "@{" in reference
        or any(ord(c) <= 32 or ord(c) == 127 or c in "~^:?*[\\" for c in reference)
        or reference.endswith(".")
        or any(
            not p or p.startswith(".") or p.endswith(".lock")
            for p in reference.split("/")
        )
        or reference.startswith("refs/")
        and not reference.startswith(("refs/heads/", "refs/tags/"))
    ):
        raise GitSourceError("git_invalid_ref")


def relative_path(value: str) -> PurePosixPath:
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
        or any(
            part in ("", "..") or part.casefold() == ".git" for part in value.split("/")
        )
    ):
        raise GitSourceError("git_invalid_path")
    return PurePosixPath(value)


def validate_source(
    repository: str,
    reference: str,
    subdir: str,
    ca_file: str | Path | None,
    ssh_agent_socket: str | Path | None,
    ssh_known_hosts: str | Path | None,
) -> Literal["https", "ssh"]:
    ssh = is_ssh(repository)
    if ssh:
        validate_ssh_url(repository)
        if ssh_agent_socket is None or ssh_known_hosts is None:
            raise GitSourceError("git_ssh_options_required")
        if ca_file is not None:
            raise GitSourceError("git_ssh_ca_unsupported")
    else:
        validate_url(repository)
        if ssh_agent_socket is not None or ssh_known_hosts is not None:
            raise GitSourceError("git_ssh_options_unsupported")
    validate_ref(reference)
    relative_path(subdir)
    return "ssh" if ssh else "https"


class GitTarget(Model):
    transport: Literal["https", "ssh"]
    repository: str
    reference: str
    subdir: str = "."
    ca_file: str | None = None
    ssh_agent_socket: str | None = None
    ssh_known_hosts: str | None = None

    @model_validator(mode="after")
    def source(self) -> "GitTarget":
        transport = validate_source(
            self.repository,
            self.reference,
            self.subdir,
            self.ca_file,
            self.ssh_agent_socket,
            self.ssh_known_hosts,
        )
        if transport != self.transport:
            raise ValueError("transport mismatch")
        for path in (self.ca_file, self.ssh_agent_socket, self.ssh_known_hosts):
            if path is not None:
                if not path.startswith("/") or "\x00" in path:
                    raise ValueError("absolute trust reference required")
        return self

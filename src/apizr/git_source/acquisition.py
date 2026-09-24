"""Acquire exactly one public HTTPS Git revision without checking out code."""

import os
import re
import shutil
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from threading import Event
from urllib.parse import unquote, urlsplit

from .models import AcquisitionLimits, GitSnapshot, GitSourceError
from .process import GitRunner

OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


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


def _resolve(advertisement: bytes, reference: str) -> str:
    refs: dict[str, str] = {}
    for line in advertisement.decode("utf-8").splitlines():
        oid, name = line.split("\t", 1)
        if not OID.fullmatch(oid) or name in refs:
            raise GitSourceError("git_invalid_advertisement")
        refs[name] = oid
    names = (
        [reference]
        if reference.startswith("refs/")
        else [f"refs/heads/{reference}", f"refs/tags/{reference}"]
    )
    candidates = [refs[name] for name in names if name in refs]
    if OID.fullmatch(reference):
        candidates.append(reference)
    if len(candidates) > 1:
        raise GitSourceError("git_ambiguous_ref")
    if not candidates:
        raise GitSourceError("git_ref_not_found")
    return candidates[0]


def _export(runner: GitRunner, commit: str, destination: Path) -> None:
    listing = runner.run(["--git-dir=objects.git", "ls-tree", "-rlz", commit])
    entries: list[tuple[str, int, PurePosixPath]] = []
    total = 0
    for record in listing.split(b"\0"):
        if not record:
            continue
        runner.check()
        metadata, name = record.split(b"\t", 1)
        mode, kind, oid, size = metadata.decode("ascii").split()
        if mode == "160000":
            raise GitSourceError("git_submodules_unsupported")
        if mode == "120000":
            raise GitSourceError("git_symlinks_unsupported")
        if mode not in ("100644", "100755") or kind != "blob" or not OID.fullmatch(oid):
            raise GitSourceError("git_invalid_tree")
        path = relative_path(name.decode("utf-8"))
        length = int(size)
        total += length
        entries.append((oid, length, path))
        if (
            length < 0
            or length > runner.limits.max_file_bytes
            or total > runner.limits.max_snapshot_bytes
            or len(entries) > runner.limits.max_files
        ):
            raise GitSourceError("git_snapshot_limit")
    payload = "".join(f"{oid}\n" for oid, _, _ in entries).encode("ascii")
    contents = runner.run(
        ["--git-dir=objects.git", "cat-file", "--batch"],
        payload=payload,
        output_limit=total + len(entries) * 100,
    )
    offset = 0
    destination.mkdir(mode=0o700)
    for oid, length, path in entries:
        runner.check()
        end = contents.index(b"\n", offset)
        if contents[offset:end] != f"{oid} blob {length}".encode("ascii"):
            raise GitSourceError("git_invalid_objects")
        offset = end + 1
        body = contents[offset : offset + length]
        if (
            len(body) != length
            or contents[offset + length : offset + length + 1] != b"\n"
        ):
            raise GitSourceError("git_invalid_objects")
        if body.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise GitSourceError("git_lfs_unsupported")
        target = destination.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        # No symlinks are ever materialized; exclusive creation also rejects
        # duplicate/case-folded filesystem aliases rather than overwriting them.
        with target.open("xb") as stream:
            stream.write(body)
        offset += length + 1
    if offset != len(contents):
        raise GitSourceError("git_invalid_objects")
    runner.check_volume()


@contextmanager
def acquire_snapshot(
    repository: str,
    reference: str,
    *,
    subdir: str = ".",
    limits: AcquisitionLimits | None = None,
    cancel: Event | None = None,
    ca_file: Path | None = None,
) -> Generator[GitSnapshot, None, None]:
    """Resolve/fetch once, export literal blobs, then remove all temporary data.

    Git is a trusted installed executable. POSIX process groups bound normal
    helpers; this is not a sandbox. ``ca_file`` explicitly adds test/private-CA
    trust, never disables TLS verification. No parent credentials are inherited.
    """
    validate_url(repository)
    validate_ref(reference)
    selected = relative_path(subdir)
    policy = AcquisitionLimits.model_validate(
        (limits or AcquisitionLimits()).model_dump(), strict=True
    )
    if os.name != "posix":
        raise GitSourceError("git_platform_unsupported")
    executable = shutil.which("git")
    if executable is None:
        raise GitSourceError("git_not_found")
    with TemporaryDirectory(prefix="apizr-git-") as directory:
        try:
            work = Path(directory)
            runner = GitRunner(
                str(Path(executable).absolute()), work, policy, cancel, ca_file
            )
            oid = _resolve(
                runner.run(["ls-remote", "--quiet", "--", repository]), reference
            )
            template = work / "empty-template"
            template.mkdir()
            runner.run(
                [
                    "init",
                    "--bare",
                    f"--template={template}",
                    f"--object-format={'sha256' if len(oid) == 64 else 'sha1'}",
                    "objects.git",
                ]
            )
            runner.run(
                [
                    "--git-dir=objects.git",
                    "fetch",
                    "--quiet",
                    "--depth=1",
                    "--no-tags",
                    "--no-recurse-submodules",
                    "--",
                    repository,
                    oid,
                ]
            )
            commit = (
                runner.run(
                    [
                        "--git-dir=objects.git",
                        "rev-parse",
                        "--verify",
                        f"{oid}^{{commit}}",
                    ]
                )
                .decode("ascii")
                .strip()
            )
            if not OID.fullmatch(commit):
                raise GitSourceError("git_invalid_commit")
            snapshot = work / "snapshot"
            _export(runner, commit, snapshot)
            root = snapshot.joinpath(*selected.parts)
            if not root.is_dir():
                raise GitSourceError("git_subdir_not_found")
            runner.check()
        except GitSourceError:
            raise
        except (OSError, ValueError, UnicodeError):
            raise GitSourceError("git_acquisition_failed") from None
        yield GitSnapshot(repository, reference, commit, selected.as_posix(), root)

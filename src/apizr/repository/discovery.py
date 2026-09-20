"""Bounded descriptor-relative traversal. Source links are never followed."""

import os
import stat
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .model import Code, Diagnostic
from .policy import ScanPolicy, relative_path


class ScanError(ValueError):
    """No valid repository anchor/policy could be established."""


class ScanLimit(Exception):
    def __init__(self, diagnostic: Diagnostic):
        self.diagnostic = diagnostic


@dataclass(frozen=True)
class SourceInput:
    path: str
    content: bytes | None
    size: int | None


@dataclass
class Budget:
    policy: ScanPolicy
    entries: int = 0
    sources: int = 0
    bytes: int = 0

    def entry(self) -> None:
        self.entries += 1
        if self.entries > self.policy.max_entries:
            raise ScanLimit(Diagnostic(code=Code.LIMIT, path=".", limit="entries"))

    def source(self) -> None:
        self.sources += 1
        if self.sources > self.policy.max_source_files:
            raise ScanLimit(Diagnostic(code=Code.LIMIT, path=".", limit="sources"))

    def content(self, size: int) -> None:
        self.bytes += size
        if self.bytes > self.policy.max_total_bytes:
            raise ScanLimit(Diagnostic(code=Code.LIMIT, path=".", limit="bytes"))


def read_source(
    parent: int, name: str, path: str, policy: ScanPolicy, budget: Budget
) -> tuple[SourceInput, Diagnostic | None]:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
    )
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise OSError("Source is not a regular file")
        if before.st_size > policy.max_file_bytes:
            return SourceInput(path, None, before.st_size), Diagnostic(
                code=Code.SIZE, path=path
            )
        # Check aggregate size before allocating another source buffer.
        budget.content(before.st_size)
        content = stream.read(policy.max_file_bytes + 1)
        after = os.fstat(stream.fileno())
        if len(content) > policy.max_file_bytes:
            return SourceInput(path, None, len(content)), Diagnostic(
                code=Code.SIZE, path=path
            )
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or len(content) != before.st_size:
            raise OSError("Source changed while reading")
        return SourceInput(path, content, len(content)), None


def discover(
    root: str | Path, policy: ScanPolicy
) -> tuple[list[SourceInput], list[Diagnostic]]:
    if os.name != "posix":
        raise ScanError(
            "Scanner v1 requires POSIX descriptor-relative filesystem access"
        )
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        anchor = os.open(root, flags)
    except OSError:
        raise ScanError(
            "Repository root must be an accessible non-symlink directory"
        ) from None
    sources: list[SourceInput] = []
    diagnostics: list[Diagnostic] = []
    budget = Budget(policy)

    def walk(descriptor: int, path: str, depth: int) -> None:
        if depth > policy.max_depth:
            raise ScanLimit(Diagnostic(code=Code.LIMIT, path=".", limit="depth"))
        names: list[str] = []
        try:
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    budget.entry()
                    # A non-UTF-8 filesystem name cannot enter canonical UTF-8 JSON.
                    try:
                        entry.name.encode("utf-8")
                    except UnicodeError:
                        diagnostics.append(Diagnostic(code=Code.READ, path=path))
                        continue
                    names.append(entry.name)
        except OSError:
            diagnostics.append(Diagnostic(code=Code.READ, path=path))
            return
        for name in sorted(names):
            try:
                relative = relative_path((PurePosixPath(path) / name).as_posix())
            except ValueError:
                diagnostics.append(Diagnostic(code=Code.MODULE, path=path))
                continue
            try:
                info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    if name in policy.excluded_directories:
                        continue
                    if stat.S_ISLNK(info.st_mode):
                        diagnostics.append(Diagnostic(code=Code.SYMLINK, path=relative))
                        continue
                    child = os.open(name, flags, dir_fd=descriptor)
                    try:
                        walk(child, relative, depth + 1)
                    finally:
                        os.close(child)
                elif PurePosixPath(name).suffix in policy.included_suffixes:
                    budget.source()
                    if not stat.S_ISREG(info.st_mode):
                        raise OSError("Source is not a regular file")
                    source, diagnostic = read_source(
                        descriptor, name, relative, policy, budget
                    )
                    sources.append(source)
                    if diagnostic:
                        diagnostics.append(diagnostic)
            except OSError:
                diagnostics.append(Diagnostic(code=Code.READ, path=relative))
                if PurePosixPath(name).suffix in policy.included_suffixes:
                    sources.append(SourceInput(relative, None, None))

    try:
        for source_root in policy.source_roots:
            with ExitStack() as stack:
                current = anchor
                try:
                    for part in PurePosixPath(source_root).parts:
                        current = os.open(part, flags, dir_fd=current)
                        stack.callback(os.close, current)
                except OSError:
                    diagnostics.append(Diagnostic(code=Code.ROOT, path=source_root))
                    continue
                walk(current, source_root, 0)
    except ScanLimit as error:
        # A partial prefix must not look like a complete inventory. Its identity
        # must not depend on an arbitrary OS enumeration prefix either.
        return [], [error.diagnostic]
    finally:
        os.close(anchor)
    return sources, diagnostics

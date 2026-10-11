"""Private, immutable canonical evidence; descriptor-relative exclusive publication."""

import os
import re
import stat
import uuid
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from apizr.contracts.distribution import Digest
from apizr.experiments.model import ExperimentPlan, ExperimentRun, ExperimentValue
from apizr.experiments.serialization import (
    MAX_ARTIFACT_BYTES,
    plan_bytes,
    plan_digest,
    run_bytes,
    run_digest,
    validate_run_binding,
)
from apizr.workspace.files import absolute_path

MAX_ENTRIES = 4096
MAX_READ_BYTES = 64 * 1024 * 1024
DEFAULT_STORE = Path(".apizr/experiments/v1")
_CANONICAL = re.compile(r"([0-9a-f]{64})\.json\Z")
_STAGING = re.compile(r"\.stage-[0-9a-f]{32}\Z")


class StoreError(ValueError):
    """Stable refusal without filenames, source text or exception details."""


class RunRecord(ExperimentValue):
    schema_version: Literal["apizr.experiment-record/v1"] = "apizr.experiment-record/v1"
    run_digest: Digest
    plan_digest: Digest
    plan: ExperimentPlan
    run: ExperimentRun

    @model_validator(mode="after")
    def bound(self) -> Self:
        validate_run_binding(self.run, self.plan)
        if self.run_digest != run_digest(self.run) or self.plan_digest != plan_digest(
            self.plan
        ):
            raise ValueError("store_digest_mismatch")
        return self


@contextmanager
def _root(path: Path, *, create: bool) -> Generator[int]:
    path = absolute_path(path)
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _child(parent: int, name: str, *, create: bool) -> Generator[int]:
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
    descriptor = os.open(
        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
    )
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _names(directory: int) -> tuple[str, ...]:
    names: list[str] = []
    with os.scandir(directory) as entries:
        for count, entry in enumerate(entries, 1):
            if count > MAX_ENTRIES:
                raise StoreError("store_limit")
            if _STAGING.fullmatch(entry.name):
                # Interrupted staging is not canonical evidence. Never repair it;
                # count it against traversal limits, and never follow its path.
                continue
            if not _CANONICAL.fullmatch(entry.name):
                raise StoreError("store_corrupt")
            names.append(entry.name)
    return tuple(sorted(names))


def _read(directory: int, name: str) -> bytes:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARTIFACT_BYTES:
            raise StoreError("store_corrupt")
        data = bytearray()
        while chunk := os.read(
            descriptor, min(65536, MAX_ARTIFACT_BYTES + 1 - len(data))
        ):
            data.extend(chunk)
            if len(data) > MAX_ARTIFACT_BYTES:
                raise StoreError("store_corrupt")
        return bytes(data)
    finally:
        os.close(descriptor)


def _publish(directory: int, name: str, payload: bytes) -> None:
    names = _names(directory)
    if name not in names and len(names) >= MAX_ENTRIES:
        raise StoreError("store_limit")
    temporary = ".stage-" + uuid.uuid4().hex
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory,
    )
    try:
        try:
            os.fchmod(descriptor, 0o600)
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("store_write_failed")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(
                temporary,
                name,
                src_dir_fd=directory,
                dst_dir_fd=directory,
                follow_symlinks=False,
            )
        except FileExistsError:
            if _read(directory, name) != payload:
                raise StoreError("store_corrupt") from None
        os.fsync(directory)
    finally:
        os.unlink(temporary, dir_fd=directory)
        os.fsync(directory)


def _initialize(root: int) -> None:
    # Lock the directory inode, not a mutable index or a path-following lock file.
    # Concurrent first writers converge; an existing partial layout is refused.
    import fcntl

    fcntl.flock(root, fcntl.LOCK_EX)
    try:
        missing: list[str] = []
        for name in ("plans", "runs"):
            try:
                os.stat(name, dir_fd=root, follow_symlinks=False)
            except FileNotFoundError:
                missing.append(name)
        if len(missing) == 1:
            raise StoreError("store_corrupt")
        for name in missing:
            with _child(root, name, create=True):
                pass
    finally:
        fcntl.flock(root, fcntl.LOCK_UN)


def records(path: Path, *, create: bool = False) -> Iterator[RunRecord]:
    """Validate all plans/runs, yielding one record at a time within fixed bounds.

    Missing store means empty history. Missing subdirectories or canonical Plans
    inside an existing store are corrupt. Concurrent publication may add a Plan
    after the initial inventory; it is validated on demand, within the same budget.
    """
    opened = False
    try:
        with _root(path, create=create) as root:
            opened = True
            if create:
                _initialize(root)
            with (
                _child(root, "plans", create=False) as plans,
                _child(root, "runs", create=False) as runs,
            ):
                budget = MAX_READ_BYTES
                cache: dict[str, ExperimentPlan] = {}

                def read(directory: int, name: str) -> bytes:
                    nonlocal budget
                    data = _read(directory, name)
                    budget -= len(data)
                    if budget < 0:
                        raise StoreError("store_limit")
                    if sha256(data).hexdigest() + ".json" != name:
                        raise StoreError("store_corrupt")
                    return data

                def load_plan(name: str) -> ExperimentPlan:
                    if name not in cache:
                        if len(cache) >= MAX_ENTRIES:
                            raise StoreError("store_limit")
                        raw = read(plans, name)
                        plan = ExperimentPlan.model_validate_json(raw)
                        if plan_bytes(plan) != raw:
                            raise StoreError("store_corrupt")
                        cache[name] = plan
                    return cache[name]

                for name in _names(plans):
                    load_plan(name)
                for name in _names(runs):
                    raw = read(runs, name)
                    run = ExperimentRun.model_validate_json(raw)
                    if run_bytes(run) != raw:
                        raise StoreError("store_corrupt")
                    plan = load_plan(run.plan_digest + ".json")
                    yield RunRecord(
                        run_digest=name[:-5],
                        plan_digest=run.plan_digest,
                        plan=plan,
                        run=run,
                    )
    except FileNotFoundError:
        # Only an absent selected root is an empty store. Never hide a missing
        # referenced plan or subdirectory, including dangling symlink roots.
        if not opened and not create:
            return
        raise StoreError("store_corrupt") from None
    except StoreError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise StoreError("store_corrupt") from None


def prepare_store(path: Path) -> None:
    for _ in records(path, create=True):
        pass


def publish(path: Path, plan: ExperimentPlan, run: ExperimentRun) -> RunRecord:
    """Validate binding before publication, durably publish Plan before Run, never replace."""
    try:
        validate_run_binding(run, plan)
        record = RunRecord(
            plan=plan,
            run=run,
            plan_digest=plan_digest(plan),
            run_digest=run_digest(run),
        )
        planned, observed = plan_bytes(plan), run_bytes(run)
        prepare_store(path)
        with _root(path, create=False) as root:
            with (
                _child(root, "plans", create=False) as plans,
                _child(root, "runs", create=False) as runs,
            ):
                _publish(plans, record.plan_digest + ".json", planned)
                _publish(runs, record.run_digest + ".json", observed)
        return record
    except StoreError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise StoreError("store_publish_failed") from None

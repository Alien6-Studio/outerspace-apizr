"""Existing configuration contracts, staged publication with configuration last."""

import json
import os
import stat
from pathlib import Path

from apizr.analysis_contracts import LocalTarget
from apizr.config_files import absolute_path, directory_fd
from apizr.exposure.policy import Execution, ExposurePolicy
from apizr.interfaces.serialization import json_bytes
from apizr.operator_policy import AnalysisGrant, OperatorPolicy
from apizr.project import ProjectConfig
from apizr.repository.policy import ScanPolicy
from apizr.repository_readiness.policy import (
    ExecutionRequirements,
    RepositoryReadinessPolicy,
)

from .models import InitError, InitResult

STAGE = ".apizr-init.stage"


def plan_initialization(
    root: str | Path, *, source_roots: tuple[str, ...] = (".",)
) -> dict[str, bytes]:
    """Pure file mapping. The caller supplies the exact absolute local root."""
    try:
        if len(source_roots) > 128 or any(
            len(root.encode("utf-8")) > 256 for root in source_roots
        ):
            raise ValueError()
        target = LocalTarget(root=str(root))
        scan = ScanPolicy(source_roots=source_roots)
        project = ProjectConfig(
            schema_version="apizr.project/v1",
            scan=scan,
            readiness_policy=Path(".apizr/policies/readiness.json"),
            exposure_policy=Path(".apizr/policies/exposure.json"),
        )
        readiness = RepositoryReadinessPolicy(
            execution=ExecutionRequirements(modes=("direct",))
        )
        exposure = ExposurePolicy(
            interfaces=("mcp", "rest"), execution=Execution(allowed=("direct",))
        )
        authority = OperatorPolicy(
            schema="apizr.operator-policy/v1",
            grants=(
                AnalysisGrant(
                    adapter="repository",
                    operation="analyze",
                    target=target,
                    permissions=("source.analyze",),
                ),
            ),
        )
        config = (
            'schema_version = "apizr.project/v1"\nroot = "."\n'
            f'readiness_policy = "{project.readiness_policy}"\n'
            f'exposure_policy = "{project.exposure_policy}"\n\n[scan]\n'
            f"source_roots = {json.dumps(list(scan.source_roots), ensure_ascii=True)}\n"
        )
        return {
            "apizr.toml": config.encode(),
            ".apizr/.gitignore": b"/operator.json\n",
            ".apizr/operator.json": json_bytes(
                authority.model_dump(mode="json", by_alias=True)
            ),
            ".apizr/policies/readiness.json": json_bytes(
                readiness.model_dump(mode="json")
            ),
            ".apizr/policies/exposure.json": json_bytes(
                exposure.model_dump(mode="json")
            ),
        }
    except (ValueError, TypeError, UnicodeError):
        raise InitError("init_target_invalid") from None


def _exists(parent: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _write(parent: int, name: str, data: bytes) -> None:
    fd = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _directory(parent: int, name: str) -> int:
    os.mkdir(name, 0o700, dir_fd=parent)
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)


def _remove_owned(parent: int, name: str, fd: int, files: tuple[str, ...]) -> None:
    """Never recursively erase unrecognized files or a substituted directory."""
    current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    saved = os.fstat(fd)
    if (current.st_dev, current.st_ino) != (saved.st_dev, saved.st_ino):
        raise InitError("init_output_conflict")
    if set(os.listdir(fd)) - set(files):
        raise InitError("init_output_conflict")
    for file in files:
        if _exists(fd, file):
            if not stat.S_ISREG(
                os.stat(file, dir_fd=fd, follow_symlinks=False).st_mode
            ):
                raise InitError("init_output_conflict")
            os.unlink(file, dir_fd=fd)
    os.rmdir(name, dir_fd=parent)


def initialize_project(
    directory: str | Path = ".", *, source_roots: tuple[str, ...] = (".",)
) -> InitResult:
    root = absolute_path(Path(directory))
    files = plan_initialization(root, source_roots=source_roots)
    started = False
    try:
        with directory_fd(root) as parent:
            if any(_exists(parent, name) for name in ("apizr.toml", ".apizr")):
                raise InitError("init_output_exists")
            if _exists(parent, STAGE):
                raise InitError("init_output_conflict")
            stage = _directory(parent, STAGE)
            started = True
            apizr = policies = None
            committed = False
            try:
                for index, data in enumerate(files.values()):
                    _write(stage, str(index), data)
                # Exclusive reservation refuses concurrently created user data.
                apizr = _directory(parent, ".apizr")
                policies = _directory(apizr, "policies")
                for index, name in enumerate(files):
                    if name == "apizr.toml":
                        continue
                    target = policies if "/policies/" in name else apizr
                    os.link(
                        str(index),
                        Path(name).name,
                        src_dir_fd=stage,
                        dst_dir_fd=target,
                        follow_symlinks=False,
                    )
                os.fsync(policies)
                os.fsync(apizr)
                # Exclusive link is the commit point: the accepted config appears last.
                os.link(
                    "0",
                    "apizr.toml",
                    src_dir_fd=stage,
                    dst_dir_fd=parent,
                    follow_symlinks=False,
                )
                committed = True
            finally:
                try:
                    # A signal can arrive immediately after the exclusive link.
                    # Recognize that commit from inode identity before rollback.
                    if _exists(stage, "0") and _exists(parent, "apizr.toml"):
                        staged = os.stat("0", dir_fd=stage, follow_symlinks=False)
                        published = os.stat(
                            "apizr.toml", dir_fd=parent, follow_symlinks=False
                        )
                        committed = (staged.st_dev, staged.st_ino) == (
                            published.st_dev,
                            published.st_ino,
                        )
                    if not committed and apizr is not None:
                        if policies is not None:
                            _remove_owned(
                                apizr,
                                "policies",
                                policies,
                                ("readiness.json", "exposure.json"),
                            )
                        _remove_owned(
                            parent, ".apizr", apizr, ("operator.json", ".gitignore")
                        )
                    _remove_owned(
                        parent, STAGE, stage, tuple(str(i) for i in range(len(files)))
                    )
                finally:
                    for fd in (policies, apizr, stage):
                        if fd is not None:
                            os.close(fd)
        return InitResult(files=tuple(files))
    except InitError:
        raise
    except KeyboardInterrupt:
        raise InitError("init_cancelled") from None
    except FileExistsError:
        raise InitError("init_output_conflict") from None
    except (OSError, ValueError):
        raise InitError(
            "init_write_failed" if started else "init_target_invalid"
        ) from None

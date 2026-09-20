"""Explicit lexical discovery policy; no packaging or SCM heuristics."""

from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from apizr.capabilities.types import ValueModel

DEFAULT_EXCLUSIONS = (
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
)


def relative_path(value: str, *, allow_root: bool = False) -> str:
    value.encode("utf-8")
    if not value or "\\" in value or "\0" in value or ".." in value.split("/"):
        raise ValueError("Expected a contained relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or PureWindowsPath(value).drive
        or (path.as_posix() == "." and not allow_root)
    ):
        raise ValueError("Expected a contained relative POSIX path")
    return path.as_posix()


class ScanPolicy(ValueModel):
    schema_version: Literal["apizr.scan/v1"] = "apizr.scan/v1"
    source_roots: tuple[str, ...] = (".",)
    included_suffixes: tuple[Literal[".py"], ...] = (".py",)
    excluded_directories: tuple[str, ...] = tuple(sorted(DEFAULT_EXCLUSIONS))
    symlinks: Literal["skip"] = "skip"
    max_file_bytes: int = Field(default=1048576, ge=1, le=16777216)
    max_source_files: int = Field(default=1000, ge=1, le=100000)
    max_total_bytes: int = Field(default=16777216, ge=1, le=268435456)
    max_entries: int = Field(default=20000, ge=1, le=1000000)
    max_depth: int = Field(default=64, ge=1, le=128)

    @field_validator("source_roots")
    @classmethod
    def roots(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("At least one source root is required")
        return tuple(sorted({relative_path(v, allow_root=True) for v in values}))

    @field_validator("excluded_directories")
    @classmethod
    def exclusions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(relative_path(v) != v or "/" in v for v in values):
            raise ValueError("Exclusions are exact directory basenames")
        return tuple(sorted(set(values)))

    @field_validator("included_suffixes")
    @classmethod
    def suffixes(cls, values: tuple[Literal[".py"], ...]) -> tuple[Literal[".py"], ...]:
        if not values:
            raise ValueError("At least one included suffix is required")
        return tuple(sorted(set(values)))

    @model_validator(mode="after")
    def disjoint_roots(self) -> Self:
        for i, root in enumerate(self.source_roots):
            if any(
                root == "." or other.startswith(root + "/")
                for other in self.source_roots[i + 1 :]
            ):
                raise ValueError("Source roots must not overlap")
        return self

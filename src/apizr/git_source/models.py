"""Explicit acquisition inputs and ephemeral snapshot identity."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import ConfigDict, Field

from apizr.capabilities.types import ValueModel


class GitSourceError(ValueError):
    """Fixed diagnostic code, never Git's output or a credential-bearing URL."""


class AcquisitionLimits(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    total_timeout_ms: int = Field(default=120000, ge=1, le=600000)
    max_stdout_bytes: int = Field(default=80 * 1024 * 1024, ge=1, le=1024**3)
    max_stderr_bytes: int = Field(default=65536, ge=1, le=1024**2)
    max_acquisition_bytes: int = Field(default=128 * 1024 * 1024, ge=1, le=1024**3)
    max_files: int = Field(default=10000, ge=1, le=100000)
    max_file_bytes: int = Field(default=8 * 1024 * 1024, ge=1, le=1024**3)
    max_snapshot_bytes: int = Field(default=64 * 1024 * 1024, ge=1, le=1024**3)


@dataclass(frozen=True)
class GitSnapshot:
    """Paths are valid only inside acquire_snapshot's context manager."""

    repository: str
    requested_ref: str
    commit: str
    subdir: str
    root: Path

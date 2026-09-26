"""Exact-generation cleanup intents, separate from the visible inventory."""

import json
import os
import stat
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field

from apizr.capabilities.types import ValueModel
from apizr.extension_runtime.protocol import unique_object

from .models import Installation, PluginError


class Retirement(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    installation: Installation
    device: int = Field(ge=0)
    inode: int = Field(gt=0)


class Retirements(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    schema_version: Literal["apizr.plugin-removals/v1"] = "apizr.plugin-removals/v1"
    pending: list[Retirement] = Field(default_factory=list[Retirement], max_length=1000)


def read(root: Path) -> Retirements:
    try:
        fd = os.open(
            root / "removals.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        )
    except FileNotFoundError:
        return Retirements()
    try:
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError()
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError()
        state = Retirements.model_validate(
            json.loads(data, object_pairs_hook=unique_object), strict=True
        )
        identities: set[tuple[str, str]] = set()
        generations: set[str] = set()
        for item in state.pending:
            record = item.installation
            identity = (record.name, record.version)
            if (
                identity in identities
                or record.environment_id in generations
                or record.python
                != str(
                    root / "environments" / record.environment_id / "venv/bin/python"
                )
            ):
                raise ValueError()
            identities.add(identity)
            generations.add(record.environment_id)
        return state
    except (ValueError, RecursionError):
        raise PluginError("invalid_removal_state") from None


def write(root: Path, pending: list[Retirement]) -> None:
    from .store import atomic_write

    raw = Retirements(pending=pending).model_dump_json(by_alias=True).encode() + b"\n"
    if len(raw) > 1024 * 1024:
        raise PluginError("removal_state_full")
    atomic_write(root / "removals.json", raw)


def refuse_pending(root: Path, name: str, version: str) -> None:
    if any(
        (p.installation.name, p.installation.version) == (name, version)
        for p in read(root).pending
    ):
        raise PluginError("plugin_cleanup_pending")

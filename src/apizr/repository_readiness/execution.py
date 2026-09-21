"""Versioned backend contract support, never host/runtime availability checks."""

from typing import Literal

from apizr.capabilities.types import ValueModel
from apizr.execution.policy import BackendCapabilities, Control

from .policy import ExecutionRequirements, Mode

# v1 local backend's declared controls, without calling local_capabilities().
_LOCAL = BackendCapabilities(available=False).enforced
# OCI v1 adds network=none and its container filesystem boundary. PID limits
# do NOT implement absolute subprocess prohibition (issue #49).
_OCI: tuple[Control, ...] = (*_LOCAL, "network_deny", "filesystem_sandbox")


class ModeCompatibility(ValueModel):
    mode: Mode
    backend_version: Literal["apizr.local-process/v1", "apizr.oci-container/v1"]
    supported_controls: tuple[Control, ...]
    missing_controls: tuple[Control, ...]
    compatible: bool
    runtime_availability: Literal["not_assessed"] = "not_assessed"


def execution_compatibility(
    requirements: ExecutionRequirements,
) -> tuple[ModeCompatibility, ...]:
    requirements = ExecutionRequirements.model_validate(
        requirements.model_dump(mode="json")
    )
    results: list[ModeCompatibility] = []
    for mode in requirements.modes:
        supported = _LOCAL if mode == "local-process" else _OCI
        missing = tuple(sorted(set(requirements.require_controls) - set(supported)))
        results.append(
            ModeCompatibility(
                mode=mode,
                backend_version=(
                    "apizr.local-process/v1"
                    if mode == "local-process"
                    else "apizr.oci-container/v1"
                ),
                supported_controls=tuple(sorted(supported)),
                missing_controls=missing,
                compatible=not missing,
            )
        )
    return tuple(results)

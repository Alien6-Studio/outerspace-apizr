"""Static adapters over reviewed backend contracts; no runtime/host probes."""

from typing import Literal

from apizr.capabilities.types import ValueModel
from apizr.execution.policy import BackendCapabilities

from .policy import Control, ExecutionRequirements, Mode

# The sole readiness guarantee adapter. Local facts come from the declared
# backend model, never local_capabilities() (which checks the host OS).
_LOCAL: tuple[Control, ...] = BackendCapabilities(available=False).enforced
# OCI v1 has no BackendCapabilities model. Map its reviewed Resources fields
# explicitly; conformance tests bind these names to that model and provider.
# PID containment is not absolute subprocess prohibition (issue #49).
OCI_RESOURCE_FIELDS: dict[Control, str] = {
    "memory_limit": "memory_bytes",
    "cpu_limit": "cpu_millis",
    "pid_limit": "pids",
}
_SUPPORTED: dict[Mode, tuple[Control, ...]] = {
    "direct": (),
    "local-process": _LOCAL,
    "oci-container": (
        *_LOCAL,
        "network_deny",
        "filesystem_sandbox",
        *OCI_RESOURCE_FIELDS,
    ),
}
BackendVersion = Literal["direct", "apizr.local-process/v1", "apizr.oci-container/v1"]
_VERSIONS: dict[Mode, BackendVersion] = {
    "direct": "direct",  # Existing ungoverned invocation, no new runtime contract.
    "local-process": "apizr.local-process/v1",
    "oci-container": "apizr.oci-container/v1",
}


class ModeCompatibility(ValueModel):
    mode: Mode
    backend_version: BackendVersion
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
    # Preserve every old policy/report byte, not just default-policy digests.
    # Old policies retain their original vocabulary projection. Explicit use of
    # any additive feature enables the complete vocabulary in the snapshot.
    extended = "direct" in requirements.modes or bool(
        set(requirements.require_controls) & OCI_RESOURCE_FIELDS.keys()
    )
    results: list[ModeCompatibility] = []
    for mode in requirements.modes:
        supported = _SUPPORTED[mode]
        missing = tuple(sorted(set(requirements.require_controls) - set(supported)))
        visible: tuple[Control, ...] = (
            supported
            if extended
            else tuple(
                control for control in supported if control not in OCI_RESOURCE_FIELDS
            )
        )
        results.append(
            ModeCompatibility(
                mode=mode,
                backend_version=_VERSIONS[mode],
                supported_controls=tuple(sorted(visible)),
                missing_controls=missing,
                compatible=not missing,
            )
        )
    return tuple(results)

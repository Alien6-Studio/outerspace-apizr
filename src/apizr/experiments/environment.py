"""Selected trusted-runtime facts and bounded root-level specification identities."""

import importlib.metadata
import os
import platform
import sys
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, field_validator

from apizr.contracts.distribution import canonical_name
from apizr.experiments.inputs import (
    DiagnosticCode,
    FingerprintPolicy,
    fingerprint_input,
)
from apizr.experiments.model import (
    EnvironmentEvidence,
    EnvironmentValue,
    EvidenceOrigin,
    ExperimentValue,
    InputArtifact,
    Name,
    PackageEvidence,
    ordered_evidence,
)
from apizr.workspace.files import directory_fd

_MAX_SPECS = 32
_MAX_ENTRIES = 4096
_APIZR = "outerspace-apizr"
_SPEC_NAMES = frozenset(
    {
        "uv.lock",
        "poetry.lock",
        "environment.yml",
        "environment.yaml",
        "conda.yml",
        "conda.yaml",
    }
)
_SPEC_POLICY = FingerprintPolicy(max_file_bytes=16 * 1024 * 1024)

EnvironmentDiagnosticCode = Literal[
    "environment_specs_limit",
    "environment_specs_unreadable",
    "environment_spec_reference_invalid",
    "environment_value_unavailable",
    "environment_package_missing",
    "environment_package_unreadable",
]


class EnvironmentDiagnostic(ExperimentValue):
    code: EnvironmentDiagnosticCode | DiagnosticCode
    name: Name | None = None


class EnvironmentResult(ExperimentValue):
    evidence: EnvironmentEvidence
    diagnostics: Annotated[
        tuple[EnvironmentDiagnostic, ...], Field(max_length=128)
    ] = ()

    @field_validator("diagnostics")
    @classmethod
    def ordered_diagnostics(
        cls, items: tuple[EnvironmentDiagnostic, ...]
    ) -> tuple[EnvironmentDiagnostic, ...]:
        return tuple(sorted(set(items), key=lambda item: (item.name or "", item.code)))


class _Selection(ExperimentValue):
    distributions: Annotated[
        tuple[Annotated[Name, AfterValidator(canonical_name)], ...],
        Field(max_length=64),
    ] = ()

    @field_validator("distributions")
    @classmethod
    def ordered_distributions(cls, items: tuple[str, ...]) -> tuple[str, ...]:
        return ordered_evidence(items, lambda item: item)


def _spec_names(root: Path) -> tuple[str, ...]:
    names: list[str] = []
    with directory_fd(root) as descriptor, os.scandir(descriptor) as entries:
        for count, entry in enumerate(entries, start=1):
            if count > _MAX_ENTRIES:
                raise ValueError("environment_specs_limit")
            name = entry.name
            if name in _SPEC_NAMES or (
                name.startswith("requirements") and name.endswith((".txt", ".lock"))
            ):
                names.append(name)
                if len(names) > _MAX_SPECS:
                    raise ValueError("environment_specs_limit")
    return tuple(sorted(names))


def _specs(
    root: Path, policy: FingerprintPolicy, origin: EvidenceOrigin
) -> EnvironmentResult:
    try:
        names = _spec_names(root)
    except ValueError:
        return EnvironmentResult(
            evidence=EnvironmentEvidence(),
            diagnostics=(EnvironmentDiagnostic(code="environment_specs_limit"),),
        )
    except OSError:
        return EnvironmentResult(
            evidence=EnvironmentEvidence(),
            diagnostics=(EnvironmentDiagnostic(code="environment_specs_unreadable"),),
        )
    try:
        # Admit the entire selection before reading any matching file.
        selections = tuple(
            InputArtifact(name=name, reference=name, origin=EvidenceOrigin.STATIC)
            for name in names
        )
    except (ValueError, UnicodeError):
        return EnvironmentResult(
            evidence=EnvironmentEvidence(),
            diagnostics=(
                EnvironmentDiagnostic(code="environment_spec_reference_invalid"),
            ),
        )
    artifacts: list[InputArtifact] = []
    diagnostics: list[EnvironmentDiagnostic] = []
    for selection in selections:
        result = fingerprint_input(root, selection, policy=policy)
        observed = result.artifacts[0]
        # This very call observed bytes; label them for the enclosing producer's
        # context. Failed observations keep unknown content, with no digest/size.
        artifacts.append(
            observed.model_copy(
                update={
                    "origin": origin,
                    "content_origin": origin
                    if observed.digest is not None
                    else EvidenceOrigin.UNKNOWN,
                }
            )
        )
        diagnostics.extend(
            EnvironmentDiagnostic(code=item.code, name=item.name)
            for item in result.diagnostics
        )
    return EnvironmentResult(
        evidence=EnvironmentEvidence(artifacts=tuple(artifacts)),
        diagnostics=tuple(diagnostics),
    )


def _policy(policy: FingerprintPolicy | None) -> FingerprintPolicy:
    return _SPEC_POLICY if policy is None else FingerprintPolicy.model_validate(policy)


def discover_environment_specs(
    root: Path, *, policy: FingerprintPolicy | None = None
) -> EnvironmentResult:
    """Static identities of at most 32 recognized files in the supplied root."""
    return _specs(root, _policy(policy), EvidenceOrigin.STATIC)


def _value(
    value: str, name: str, diagnostics: list[EnvironmentDiagnostic]
) -> EnvironmentValue:
    try:
        return EnvironmentValue(value=value, origin=EvidenceOrigin.RUNTIME)
    except (ValueError, UnicodeError):
        diagnostics.append(
            EnvironmentDiagnostic(code="environment_value_unavailable", name=name)
        )
        return EnvironmentValue(value=None, origin=EvidenceOrigin.UNKNOWN)


def capture_runtime_environment(
    *,
    distributions: tuple[str, ...] = (),
    root: Path | None = None,
    policy: FingerprintPolicy | None = None,
) -> EnvironmentResult:
    """Observe this trusted process, selected metadata and optional root specs.

    No distribution imports, dependency resolution, env-var snapshot, GPU probe,
    or project execution. This function does not construct an Experiment Run.
    """
    try:
        selected = _Selection(distributions=distributions).distributions
        admitted_policy = _policy(policy)
    except (ValueError, UnicodeError):
        raise ValueError("environment_selection_invalid") from None
    diagnostics: list[EnvironmentDiagnostic] = []
    packages: list[PackageEvidence] = []
    for name in sorted({_APIZR, *selected}):
        try:
            version = importlib.metadata.version(name)
            packages.append(
                PackageEvidence(
                    name=name, version=version, origin=EvidenceOrigin.RUNTIME
                )
            )
            continue
        except importlib.metadata.PackageNotFoundError:
            code = "environment_package_missing"
        except (ValueError, UnicodeError, OSError):
            code = "environment_package_unreadable"
        packages.append(
            PackageEvidence(name=name, version=None, origin=EvidenceOrigin.UNKNOWN)
        )
        diagnostics.append(EnvironmentDiagnostic(code=code, name=name))
    try:
        machine = platform.machine()
    except OSError:
        machine = ""
    version_info = sys.version_info
    python_version = f"{version_info.major}.{version_info.minor}.{version_info.micro}"
    if version_info.releaselevel != "final":
        python_version += {"alpha": "a", "beta": "b", "candidate": "rc"}[
            version_info.releaselevel
        ] + str(version_info.serial)
    values = {
        "python_implementation": _value(
            sys.implementation.name, "python_implementation", diagnostics
        ),
        "python_version": _value(python_version, "python_version", diagnostics),
        "platform": _value(sys.platform, "platform", diagnostics),
        "architecture": _value(machine, "architecture", diagnostics),
    }
    specs = (
        _specs(root, admitted_policy, EvidenceOrigin.RUNTIME)
        if root is not None
        else EnvironmentResult(evidence=EnvironmentEvidence())
    )
    return EnvironmentResult(
        evidence=EnvironmentEvidence(
            **values, packages=tuple(packages), artifacts=specs.evidence.artifacts
        ),
        diagnostics=(*diagnostics, *specs.diagnostics),
    )

"""Derived Run-to-serving evidence and pure cross-domain binding validation."""

from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from apizr.capabilities.model import Digest
from apizr.contracts.application import ApplicationConfig, ApplicationInputs
from apizr.contracts.distribution import Digest as ExperimentDigest
from apizr.contracts.distribution import canonical_name
from apizr.contracts.json import encode
from apizr.experiments.model import (
    EvidenceOrigin,
    ExperimentValue,
    OutputArtifact,
    SourceIdentity,
    ordered_evidence,
)
from apizr.experiments.store import RunRecord
from apizr.exposure import ExposurePlan
from apizr.exposure.policy import Interface, capability_id
from apizr.repository.serialization import canonical_bytes
from apizr.repository_interfaces.model import RepositoryInterface

EXPOSURE_FILE = "experiment-exposure.json"
MAX_BINDING_BYTES = 1024 * 1024


class ExperimentExposureRefused(ValueError):
    """Stable bridge refusal, without project paths or source/exception contents."""


def selected_dependencies(record: RunRecord, names: tuple[str, ...]) -> tuple[str, ...]:
    """Only explicitly selected, observed Run versions; no environment lookup."""
    try:
        normalized = tuple(canonical_name(name) for name in names)
    except ValueError:
        raise ExperimentExposureRefused("run_dependency_invalid") from None
    if len(set(normalized)) != len(normalized):
        raise ExperimentExposureRefused("run_dependency_duplicate")
    packages = {
        package.name: package
        for package in (
            record.run.environment.packages if record.run.environment else ()
        )
    }
    pins: list[str] = []
    for name in normalized:
        package = packages.get(name)
        if (
            package is None
            or package.version is None
            or package.origin != EvidenceOrigin.RUNTIME
        ):
            raise ExperimentExposureRefused("run_dependency_unobserved")
        pins.append(name + "==" + package.version)
    try:
        return ApplicationConfig(dependencies=tuple(pins)).dependencies
    except ValueError:
        raise ExperimentExposureRefused("run_dependency_invalid") from None


class ExperimentExposureBinding(ExperimentValue):
    schema_version: Literal["apizr.experiment-exposure/v1"] = (
        "apizr.experiment-exposure/v1"
    )
    run_digest: ExperimentDigest
    plan_digest: ExperimentDigest
    source: SourceIdentity
    repository_digest: Digest
    catalog_digest: Digest
    graph_digest: Digest
    repository_readiness_digest: Digest
    exposure_plan_digest: Digest
    repository_interface_digest: Digest
    capability: str
    interface: Interface
    outputs: Annotated[tuple[OutputArtifact, ...], Field(max_length=128)] = ()
    dependencies: Annotated[tuple[str, ...], Field(max_length=128)] = ()
    application_inputs_digest: Digest | None = None

    _capability = field_validator("capability")(capability_id)

    @field_validator(
        "repository_digest",
        "catalog_digest",
        "graph_digest",
        "repository_readiness_digest",
        "exposure_plan_digest",
        "repository_interface_digest",
        "application_inputs_digest",
    )
    @classmethod
    def validated_digest(cls, value: Digest | None) -> Digest | None:
        # Shared Digest models are frozen but do not revalidate model_copy inputs.
        return Digest.model_validate(value.model_dump()) if value is not None else None

    @field_validator("outputs")
    @classmethod
    def selected_outputs(
        cls, values: tuple[OutputArtifact, ...]
    ) -> tuple[OutputArtifact, ...]:
        result = ordered_evidence(values, lambda item: item.name)
        ApplicationConfig(resources=tuple(item.reference or "" for item in result))
        return result

    @field_validator("dependencies")
    @classmethod
    def exact_pins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return ApplicationConfig(dependencies=values).dependencies

    @model_validator(mode="after")
    def application_presence(self) -> Self:
        if bool(self.outputs or self.dependencies) != (
            self.application_inputs_digest is not None
        ):
            raise ValueError("experiment_application_binding_missing")
        return self


class ExperimentExposureResult(ExperimentValue):
    """Portable bundle identity; filesystem destinations are presentation only."""

    binding: ExperimentExposureBinding
    bundle_manifest_digest: Digest


def exposure_bytes(binding: ExperimentExposureBinding) -> bytes:
    binding = ExperimentExposureBinding.model_validate(binding)
    return encode(binding.model_dump(mode="json"), MAX_BINDING_BYTES)


def validate_exposure_binding(
    binding: ExperimentExposureBinding,
    record: RunRecord,
    contract: RepositoryInterface,
    exposure: ExposurePlan,
    application: ApplicationInputs | None,
) -> ExperimentExposureBinding:
    """Validate exact retained identities without I/O, execution or new evidence."""
    binding = ExperimentExposureBinding.model_validate(binding)
    record = RunRecord.model_validate(record)
    contract = RepositoryInterface.model_validate_json(contract.model_dump_json())
    exposure = ExposurePlan.model_validate_json(exposure.model_dump_json())
    if application is not None:
        application = ApplicationInputs.model_validate_json(
            application.model_dump_json()
        )
    if record.run.status != "success":
        raise ExperimentExposureRefused("run_not_successful")
    if (
        binding.run_digest != record.run_digest
        or binding.plan_digest != record.plan_digest
        or binding.source != record.run.subject
        or binding.repository_interface_digest
        != Digest.of_bytes(canonical_bytes(contract))
        or binding.exposure_plan_digest != Digest.of_bytes(canonical_bytes(exposure))
        or contract.exposure_plan_digest != binding.exposure_plan_digest
        or binding.interface != contract.interface
        or exposure.interfaces != (binding.interface,)
        or tuple(c.capability_id for c in contract.capabilities)
        != (binding.capability,)
        or tuple(c.capability_id for c in exposure.capabilities)
        != (binding.capability,)
        or contract.application != application
    ):
        raise ExperimentExposureRefused("experiment_exposure_binding_mismatch")
    for field in (
        "repository_digest",
        "catalog_digest",
        "graph_digest",
        "repository_readiness_digest",
    ):
        if getattr(binding, field) != getattr(contract, field) or getattr(
            binding, field
        ) != getattr(exposure, field):
            raise ExperimentExposureRefused("experiment_repository_binding_mismatch")
    selected_source = next(
        (s for s in contract.sources if s.module == binding.capability.split(":")[1]),
        None,
    )
    expected_digest = (
        binding.source.executable_digest
        if binding.source.kind == "notebook"
        else binding.source.digest
    )
    if (
        selected_source is None
        or selected_source.module != binding.source.module
        or selected_source.source_digest.value != expected_digest
        or (
            binding.source.kind == "python"
            and selected_source.source_path != binding.source.reference
        )
        or selected_source.source_path != exposure.capabilities[0].source_path
    ):
        raise ExperimentExposureRefused("experiment_source_binding_mismatch")
    outputs = {output.name: output for output in record.run.outputs}
    if any(outputs.get(output.name) != output for output in binding.outputs):
        raise ExperimentExposureRefused("experiment_output_binding_mismatch")
    if (
        selected_dependencies(
            record, tuple(pin.split("==")[0] for pin in binding.dependencies)
        )
        != binding.dependencies
    ):
        raise ExperimentExposureRefused("experiment_dependency_binding_mismatch")
    if binding.application_inputs_digest != (
        Digest.of_bytes(canonical_bytes(application)) if application else None
    ):
        raise ExperimentExposureRefused("experiment_application_binding_mismatch")
    if application is not None:
        resources = {resource.path: resource for resource in application.resources}
        if application.dependencies != binding.dependencies or set(resources) != {
            o.reference for o in binding.outputs
        }:
            raise ExperimentExposureRefused("experiment_application_binding_mismatch")
        for output in binding.outputs:
            assert output.reference is not None
            resource = resources[output.reference]
            if resource.digest.value != output.digest or (
                output.size is not None and resource.size != output.size
            ):
                raise ExperimentExposureRefused("experiment_output_binding_mismatch")
    return binding

"""Compact evidence snapshots; only successfully planned selections are artifacts."""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from apizr.capabilities.model import Digest, Effects
from apizr.capabilities.types import ValueModel, logical_module
from apizr.graph.model import Diagnostic, Graph, ImportDeclaration, Relationship
from apizr.readiness.model import State
from apizr.repository.policy import relative_path
from apizr.repository_readiness.model import DeclarationAssessment, Reason
from apizr.repository_readiness.policy import Mode

from .policy import Interface
from .policy import capability_id as validate_capability_id


class RelationshipEvidence(ValueModel):
    state: Literal["resolved", "partial", "unavailable"]
    diagnostics: tuple[Diagnostic, ...]
    direct: tuple[Relationship, ...]
    module_imports: tuple[Relationship, ...]
    imports: tuple[ImportDeclaration, ...]

    @field_validator("diagnostics")
    @classmethod
    def ordered_diagnostics(
        cls, values: tuple[Diagnostic, ...]
    ) -> tuple[Diagnostic, ...]:
        return Graph.ordered_diagnostics(values)

    @field_validator("direct", "module_imports")
    @classmethod
    def ordered_relationships(
        cls, values: tuple[Relationship, ...]
    ) -> tuple[Relationship, ...]:
        return Graph.ordered_edges(values)

    @field_validator("imports")
    @classmethod
    def ordered_imports(
        cls, values: tuple[ImportDeclaration, ...]
    ) -> tuple[ImportDeclaration, ...]:
        return Graph.ordered_imports(values)


class ExposureRecord(ValueModel):
    capability_id: str = Field(
        description="Exact canonical ID of this selected capability proposal; dependencies are not implicitly selected."
    )
    module: str = Field(
        description="Logical Python module owning the selected capability."
    )
    source_path: str = Field(
        description="Repository-relative source path for this static capability evidence, not an authorized filesystem target."
    )
    repository_readiness: Literal[State.READY, State.CONDITIONAL] = Field(
        description="Readiness of the selected capability's required repository evidence. CONDITIONAL requires explicit policy allowance and is not READY or proof of successful execution."
    )
    readiness_reasons: tuple[Reason, ...] = Field(
        description="Retained reasons supporting the selected-scope readiness assessment, including conditional evidence."
    )
    requested_interfaces: tuple[Interface, ...] = Field(
        min_length=1,
        description="Interfaces explicitly requested by the proposal policy for this capability.",
    )
    compatible_interfaces: tuple[Interface, ...] = Field(
        min_length=1,
        description="Requested interfaces that pass static compatibility checks; every requested interface must be compatible in a successful plan.",
    )
    compatible_execution_modes: tuple[Mode, ...] = Field(
        min_length=1,
        description="Modes satisfying both the proposal's allowed modes/required controls and the readiness policy. No ranking, fallback or execution authority is implied.",
    )
    effects: Effects = Field(
        description="Retained static effect evidence, including unknown effects; not observations from executing the capability."
    )
    relationships: RelationshipEvidence = Field(
        description="Retained static relationship and import evidence used by this capability proposal."
    )

    _path = field_validator("source_path")(relative_path)
    _id = field_validator("capability_id")(validate_capability_id)

    @field_validator("readiness_reasons")
    @classmethod
    def ordered_reasons(cls, values: tuple[Reason, ...]) -> tuple[Reason, ...]:
        return DeclarationAssessment.ordered(values)

    @field_validator(
        "requested_interfaces", "compatible_interfaces", "compatible_execution_modes"
    )
    @classmethod
    def ordered(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(values)))

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.module != self.capability_id.split(":")[1]:
            raise ValueError("Exposure record module/identity mismatch")
        if self.requested_interfaces != self.compatible_interfaces:
            raise ValueError("Every requested interface must be compatible")
        return self


class ExposurePlan(ValueModel):
    schema_version: Literal["apizr.exposure-plan/v1"] = Field(
        default="apizr.exposure-plan/v1",
        description="Version of this successful exposure proposal contract. A plan is not generation, execution, publication or authorization.",
    )
    repository_digest: Digest = Field(
        description="Repository evidence identity against which this proposal was assessed; value can pin a subsequent call."
    )
    catalog_digest: Digest = Field(
        description="Identity of the complete canonical static Catalog used for this proposal."
    )
    graph_digest: Digest = Field(
        description="Identity of the complete canonical static relationship/import Graph used for this proposal."
    )
    repository_readiness_digest: Digest = Field(
        description="Identity of the canonical repository readiness assessment used for this proposal."
    )
    exposure_policy_digest: Digest = Field(
        description="Identity of the exposure selection and execution constraints used for planning, not operator authority."
    )
    interfaces: tuple[Interface, ...] = Field(
        min_length=1,
        description="Requested interfaces validated for all selected capabilities; none has been generated, deployed or run by planning.",
    )
    capabilities: tuple[ExposureRecord, ...] = Field(
        description="Selected capability proposals with their readiness evidence, interface compatibility and compatible execution modes; not an execution or publication grant."
    )
    observed_support_modules: tuple[str, ...] = Field(
        description="Logical support modules observed in the selected static evidence; these are not additional exposed capabilities."
    )
    external_modules: tuple[str, ...] = Field(
        description="Lexically observed external module names; this does not resolve, install or authorize dependencies."
    )

    @field_validator("interfaces")
    @classmethod
    def ordered_interfaces(cls, values: tuple[Interface, ...]) -> tuple[Interface, ...]:
        return tuple(sorted(set(values)))

    @field_validator("observed_support_modules", "external_modules")
    @classmethod
    def modules(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if logical_module(value) != value:
                raise ValueError("Noncanonical module name")
        return tuple(sorted(set(values)))

    @field_validator("capabilities")
    @classmethod
    def records(cls, values: tuple[ExposureRecord, ...]) -> tuple[ExposureRecord, ...]:
        if len({value.capability_id for value in values}) != len(values):
            raise ValueError("Duplicate exposure identities")
        return tuple(sorted(values, key=lambda value: value.capability_id))

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if any(c.requested_interfaces != self.interfaces for c in self.capabilities):
            raise ValueError("Record interfaces disagree with plan")
        return self

    def capability_ids(self) -> tuple[str, ...]:
        return tuple(c.capability_id for c in self.capabilities)

    def for_interface(self, interface: Interface) -> tuple[ExposureRecord, ...]:
        return tuple(
            c for c in self.capabilities if interface in c.compatible_interfaces
        )

    def compatible_with(self, mode: Mode) -> tuple[ExposureRecord, ...]:
        return tuple(
            c for c in self.capabilities if mode in c.compatible_execution_modes
        )

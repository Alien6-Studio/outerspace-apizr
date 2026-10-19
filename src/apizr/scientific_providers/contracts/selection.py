"""Explicit provider choices and portable provenance; no discovery or invocation."""

from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from apizr.contracts.json import encode
from apizr.experiments.model import ExperimentValue, Name, Parameter
from apizr.scientific_providers.contracts.model import (
    ProducerIdentity,
    ProviderDescriptor,
    StaticCapability,
)

CAPABILITIES: tuple[StaticCapability, ...] = (
    "input_reads",
    "metric_signals",
    "output_candidates",
    "randomness_controls",
)
ProviderCode = Literal[
    "provider_disabled",
    "provider_unavailable",
    "provider_incompatible",
    "provider_failed",
    "provider_result_invalid",
    "provider_limit",
    "provider_unsupported",
    "provider_shadowed",
]


class ProviderChoice(ExperimentValue):
    identity: ProducerIdentity
    capabilities: Annotated[
        tuple[StaticCapability, ...], Field(min_length=1, max_length=4)
    ] = CAPABILITIES
    enabled: bool = True
    extension: Name | None = None

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("provider_capability_duplicate")
        if self.identity.name == "apizr.builtin" and self.extension is not None:
            raise ValueError("provider_builtin_reserved")
        return self


class ProviderSelection(ExperimentValue):
    schema_version: Literal["apizr.provider-selection/v1"] = (
        "apizr.provider-selection/v1"
    )
    providers: Annotated[tuple[ProviderChoice, ...], Field(max_length=16)] = (
        ProviderChoice(identity=ProducerIdentity(name="apizr.builtin", version="1")),
    )

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({p.identity.name for p in self.providers}) != len(self.providers):
            raise ValueError("provider_identity_duplicate")
        return self


class ProviderObservation(ExperimentValue):
    choice: ProviderChoice
    descriptor: ProviderDescriptor | None = None
    selected_capabilities: Annotated[
        tuple[StaticCapability, ...], Field(max_length=4)
    ] = ()
    diagnostic: ProviderCode | None = None

    @property
    def active(self) -> bool:
        return bool(self.selected_capabilities) and self.diagnostic is None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        selected = set(self.selected_capabilities)
        if len(selected) != len(self.selected_capabilities) or not selected <= set(
            self.choice.capabilities
        ):
            raise ValueError("provider_selection_invalid")
        if (
            self.descriptor is not None
            and self.descriptor.identity != self.choice.identity
        ):
            raise ValueError("provider_identity_mismatch")
        if self.diagnostic is None and (
            not self.choice.enabled
            or self.descriptor is None
            or not selected
            or not selected <= set(self.descriptor.capabilities)
        ):
            raise ValueError("provider_active_invalid")
        if not self.choice.enabled and self.diagnostic != "provider_disabled":
            raise ValueError("provider_disabled_invalid")
        return self


class CapabilityOwner(ExperimentValue):
    capability: StaticCapability
    provider: ProducerIdentity | None
    state: Literal["static", "unknown"]


class ProviderReport(ExperimentValue):
    schema_version: Literal["apizr.scientific-providers/v1"] = (
        "apizr.scientific-providers/v1"
    )
    providers: Annotated[tuple[ProviderObservation, ...], Field(max_length=16)]
    available: Annotated[tuple[ProducerIdentity, ...], Field(max_length=16)]
    active: Annotated[tuple[ProducerIdentity, ...], Field(max_length=16)]
    owners: Annotated[tuple[CapabilityOwner, ...], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        choices = tuple(p.choice for p in self.providers)
        ProviderSelection(providers=choices)
        if self.available != tuple(
            p.choice.identity for p in self.providers if p.descriptor is not None
        ) or self.active != tuple(
            p.choice.identity for p in self.providers if p.active
        ):
            raise ValueError("provider_inventory_mismatch")
        if tuple(o.capability for o in self.owners) != CAPABILITIES:
            raise ValueError("provider_owners_invalid")
        for owner in self.owners:
            selected = next(
                (
                    p
                    for p in self.providers
                    if owner.capability in p.choice.capabilities
                ),
                None,
            )
            if owner.provider != (
                selected.choice.identity if selected else None
            ) or owner.state != (
                "static" if selected and selected.active else "unknown"
            ):
                raise ValueError("provider_owner_mismatch")
        for p in self.providers:
            expected = tuple(
                o.capability for o in self.owners if o.provider == p.choice.identity
            )
            if p.selected_capabilities != expected:
                raise ValueError("provider_precedence_mismatch")
        return self


def read_provenance(controls: tuple[Parameter, ...]) -> ProviderReport | None:
    """Read a retained Plan's exact provider snapshot without loading providers."""
    for control in controls:
        if control.name == "scientific_providers":
            value = control.model_dump(mode="json")["value"]
            if isinstance(value, dict):
                fields = cast(dict[str, object], value)
                if fields.get("schema_version") == "apizr.scientific-providers/v1":
                    return ProviderReport.model_validate_json(encode(fields, 65536))
    return None

"""Bounded lexical randomness evidence; presence never proves execution."""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from apizr.experiments._lexical import MAX_SOURCE_BYTES as MAX_SOURCE_BYTES
from apizr.experiments.model import (
    EvidenceOrigin,
    ExperimentValue,
    Name,
    RandomnessControl,
    Reference,
    ordered_evidence,
)

RandomnessDiagnosticCode = Literal[
    "dynamic_randomness_control",
    "uncontrolled_randomness",
    "unsupported_randomness_literal",
    "unsupported_randomness_arguments",
    "randomness_control_conflict",
    "randomness_control_name_invalid",
    "randomness_source_invalid",
    "randomness_discovery_limit",
    "framework_determinism_unknown",
]


class RandomnessDiagnostic(ExperimentValue):
    code: RandomnessDiagnosticCode
    source: Reference | None = None
    line: Annotated[int, Field(ge=1, le=MAX_SOURCE_BYTES)] | None = None
    column: Annotated[int, Field(ge=0, le=MAX_SOURCE_BYTES)] | None = None


class RandomnessResult(ExperimentValue):
    """Static controls, redacted diagnostics, and versionless import candidates."""

    controls: Annotated[tuple[RandomnessControl, ...], Field(max_length=128)] = ()
    diagnostics: Annotated[tuple[RandomnessDiagnostic, ...], Field(max_length=512)] = ()
    relevant_distributions: Annotated[tuple[Name, ...], Field(max_length=6)] = ()

    @field_validator("controls")
    @classmethod
    def ordered_controls(
        cls, items: tuple[RandomnessControl, ...]
    ) -> tuple[RandomnessControl, ...]:
        if any(
            item.origin not in {EvidenceOrigin.STATIC, EvidenceOrigin.UNKNOWN}
            for item in items
        ):
            raise ValueError("randomness_origin_invalid")
        return ordered_evidence(items, lambda item: (item.provider, item.name))

    @field_validator("diagnostics")
    @classmethod
    def ordered_diagnostics(
        cls, items: tuple[RandomnessDiagnostic, ...]
    ) -> tuple[RandomnessDiagnostic, ...]:
        return tuple(
            sorted(
                set(items),
                key=lambda item: (
                    item.source or "",
                    item.line or 0,
                    item.column or 0,
                    item.code,
                ),
            )
        )

    @field_validator("relevant_distributions")
    @classmethod
    def ordered_distributions(cls, items: tuple[str, ...]) -> tuple[str, ...]:
        if any(
            item
            not in {"numpy", "pandas", "scikit-learn", "joblib", "torch", "tensorflow"}
            for item in items
        ):
            raise ValueError("randomness_distribution_invalid")
        return ordered_evidence(items, lambda item: item)


def discover_randomness(
    source: str | bytes, *, source_reference: str
) -> RandomnessResult:
    """Dispatch to the official built-in recognizer, installed with the core."""
    from apizr.scientific_providers.builtin.randomness import (
        discover_randomness as recognize,
    )

    return recognize(source, source_reference=source_reference)

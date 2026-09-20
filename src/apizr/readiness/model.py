"""Versioned policy results, separate from the immutable capability contract."""

from enum import Enum
from typing import Literal, Self

from pydantic import field_validator, model_validator

from apizr.capabilities.model import Digest, Effects, Source, SourceSpan
from apizr.capabilities.types import Evidence, ValueModel


class State(str, Enum):
    READY = "ready"
    CONDITIONAL = "conditional"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"


class Code(str, Enum):
    CONDITIONAL = "APIZR-READY-001"
    DECORATOR = "APIZR-READY-002"
    REBOUND = "APIZR-READY-003"
    INITIALIZATION = "APIZR-READY-004"
    GENERATOR = "APIZR-READY-005"
    ASYNC_GENERATOR = "APIZR-READY-006"
    UNCONSTRAINED = "APIZR-READY-007"
    NAMESPACE = "APIZR-READY-008"
    DUPLICATE = "APIZR-READY-009"
    OVERLOAD = "APIZR-READY-010"
    VARIADIC = "APIZR-READY-011"
    NON_JSON = "APIZR-READY-012"
    UNRESOLVED_TYPE = "APIZR-READY-013"
    DYNAMIC_IMPORT = "APIZR-READY-014"
    DEPENDENCY = "APIZR-READY-015"
    OUTPUT = "APIZR-READY-016"
    METADATA = "APIZR-READY-017"
    CONSTRUCT = "APIZR-READY-018"


POLICY: dict[Code, tuple[State, str]] = {
    Code.CONDITIONAL: (State.CONDITIONAL, "Definition is under module control flow."),
    Code.DECORATOR: (State.CONDITIONAL, "Decorator may replace the runtime binding."),
    Code.REBOUND: (
        State.CONDITIONAL,
        "A later statement may rebind or delete the callable name.",
    ),
    Code.INITIALIZATION: (
        State.CONDITIONAL,
        "Module initialization may abort or alter callable availability.",
    ),
    Code.GENERATOR: (
        State.UNSUPPORTED,
        "Generator requires a streaming/value adapter.",
    ),
    Code.ASYNC_GENERATOR: (
        State.UNSUPPORTED,
        "Async generator requires a streaming/value adapter.",
    ),
    Code.UNCONSTRAINED: (
        State.READY,
        "Input is unconstrained JSON; no stronger validation is established.",
    ),
    Code.NAMESPACE: (
        State.CONDITIONAL,
        "Dynamic module namespace binding is unresolved.",
    ),
    Code.DUPLICATE: (
        State.AMBIGUOUS,
        "Duplicate definitions do not identify one callable contract.",
    ),
    Code.OVERLOAD: (
        State.AMBIGUOUS,
        "Overload association does not identify one callable contract.",
    ),
    Code.VARIADIC: (
        State.UNSUPPORTED,
        "Variadic input has no supported fixed interface contract.",
    ),
    Code.NON_JSON: (
        State.UNSUPPORTED,
        "Input requires an adapter outside the ordinary JSON contract.",
    ),
    Code.UNRESOLVED_TYPE: (
        State.CONDITIONAL,
        "Runtime input type cannot be resolved from static declarations.",
    ),
    Code.DYNAMIC_IMPORT: (
        State.CONDITIONAL,
        "Dynamic import dependencies are unresolved.",
    ),
    Code.DEPENDENCY: (
        State.CONDITIONAL,
        "Local, namespace or external import dependencies are unresolved.",
    ),
    Code.OUTPUT: (
        State.READY,
        "Response schema is unknown; return annotations are not enforced.",
    ),
    Code.METADATA: (
        State.CONDITIONAL,
        "Annotation metadata constraints have no established adapter semantics.",
    ),
    Code.CONSTRUCT: (
        State.UNSUPPORTED,
        "Callable construct has no supported IR function contract.",
    ),
}
RANK = {State.READY: 0, State.CONDITIONAL: 1, State.UNSUPPORTED: 2, State.AMBIGUOUS: 3}


def combine(states: tuple[State, ...]) -> State:
    return max(states, key=RANK.__getitem__, default=State.READY)


class Reason(ValueModel):
    code: Code
    line: int
    parameter: str | None = None
    evidence: Literal[Evidence.INFERRED] = Evidence.INFERRED

    @property
    def message(self) -> str:
        return POLICY[self.code][1]


class Dimension(ValueModel):
    state: State
    reasons: tuple[Reason, ...] = ()

    @classmethod
    def assess(cls, reasons: tuple[Reason, ...] = ()) -> Self:
        return cls(
            state=combine(tuple(POLICY[r.code][0] for r in reasons)), reasons=reasons
        )

    @field_validator("reasons")
    @classmethod
    def ordered(cls, reasons: tuple[Reason, ...]) -> tuple[Reason, ...]:
        return tuple(
            sorted(
                set(reasons), key=lambda r: (r.line, r.code.value, r.parameter or "")
            )
        )

    @model_validator(mode="after")
    def derived(self) -> Self:
        if self.state != combine(tuple(POLICY[r.code][0] for r in self.reasons)):
            raise ValueError("Dimension state must derive from its reasons")
        return self


class Dimensions(ValueModel):
    binding: Dimension
    execution: Dimension
    inputs: Dimension
    outputs: Dimension

    @property
    def state(self) -> State:
        return combine(
            (
                self.binding.state,
                self.execution.state,
                self.inputs.state,
                self.outputs.state,
            )
        )


class Assessment(ValueModel):
    capability_id: str
    source: SourceSpan
    in_ir: bool
    dimensions: Dimensions
    effects: Effects
    state: State
    can_generate_interface: bool

    @model_validator(mode="after")
    def derived(self) -> Self:
        if self.state != self.dimensions.state:
            raise ValueError("Overall state must derive from dimensions")
        if self.can_generate_interface != (self.in_ir and self.state == State.READY):
            raise ValueError("Eligibility must derive from state and IR membership")
        if self.capability_id != f"python:{self.source.module}:{self.source.symbol}":
            raise ValueError("Readiness identity must match its source")
        return self


class ReadinessReport(ValueModel):
    policy_version: Literal["apizr.readiness/v1"] = "apizr.readiness/v1"
    source: Source
    ir_digest: Digest
    assessments: tuple[Assessment, ...]

    @field_validator("assessments")
    @classmethod
    def ordered_unique(cls, values: tuple[Assessment, ...]) -> tuple[Assessment, ...]:
        if len({a.capability_id for a in values}) != len(values):
            raise ValueError("Duplicate readiness identities")
        return tuple(sorted(values, key=lambda a: a.capability_id))

    @model_validator(mode="after")
    def consistent_source(self) -> Self:
        if any(a.source.module != self.source.module for a in self.assessments):
            raise ValueError("Readiness source modules must agree")
        return self

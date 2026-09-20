"""Capability IR v1 domain models, independent of all generation frameworks."""

import hashlib
from enum import Enum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .types import DeclaredType, Evidence, Expression, ValueModel, logical_module


class Digest(ValueModel):
    algorithm: Literal["sha256"] = "sha256"
    value: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def of_bytes(cls, content: bytes) -> Self:
        return cls(value=hashlib.sha256(content).hexdigest())


class Source(ValueModel):
    kind: Literal["python", "notebook"]
    module: str
    digest: Digest
    transformed_digest: Digest | None = None

    _module = field_validator("module")(logical_module)

    @model_validator(mode="after")
    def transformation_matches_kind(self) -> Self:
        if (self.kind == "notebook") != (self.transformed_digest is not None):
            raise ValueError(
                "Only notebook sources require a transformed Python digest"
            )
        return self


class SourceSpan(ValueModel):
    module: str
    symbol: str
    line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    _module = field_validator("module")(logical_module)
    _symbol = field_validator("symbol")(logical_module)

    @model_validator(mode="after")
    def ordered_lines(self) -> Self:
        if self.end_line < self.line:
            raise ValueError("End line precedes definition")
        return self


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DiagnosticCode(str, Enum):
    DUPLICATE = "APIZR-CAP-001"
    VARIADIC = "APIZR-CAP-002"
    CONDITIONAL = "APIZR-CAP-003"
    OVERLOAD = "APIZR-CAP-004"
    BINDING = "APIZR-CAP-005"
    TYPE_STRUCTURE = "APIZR-CAP-006"


class Diagnostic(ValueModel):
    code: DiagnosticCode
    severity: Severity
    message: str
    source: SourceSpan


class ExecutionForm(str, Enum):
    SYNC = "sync"
    ASYNC = "async"
    GENERATOR = "generator"
    ASYNC_GENERATOR = "async_generator"


class ParameterKind(str, Enum):
    POSITIONAL_ONLY = "positional_only"
    POSITIONAL_OR_KEYWORD = "positional_or_keyword"
    KEYWORD_ONLY = "keyword_only"


class Parameter(ValueModel):
    name: str
    kind: ParameterKind
    required: bool
    annotation: DeclaredType | None = None
    default: Expression | None = None
    evidence: Evidence = Evidence.OBSERVED

    @model_validator(mode="after")
    def consistent_default(self) -> Self:
        if self.required != (self.default is None):
            raise ValueError("Required must agree with absence of a default")
        return self


class Returns(ValueModel):
    annotation: DeclaredType | None = None
    enforcement: Literal["none"] = "none"


class Signature(ValueModel):
    parameters: tuple[Parameter, ...] = ()
    returns: Returns = Field(default_factory=Returns)

    @field_validator("parameters")
    @classmethod
    def unique_parameters(cls, values: tuple[Parameter, ...]) -> tuple[Parameter, ...]:
        if len({p.name for p in values}) != len(values):
            raise ValueError("Duplicate parameter names")
        return values


class EffectValue(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class Effect(ValueModel):
    value: EffectValue = EffectValue.UNKNOWN
    evidence: Evidence = Evidence.UNKNOWN

    @model_validator(mode="after")
    def unknown_evidence(self) -> Self:
        if (self.value == EffectValue.UNKNOWN) != (self.evidence == Evidence.UNKNOWN):
            raise ValueError("Unknown effects and unknown evidence must agree")
        return self


class Effects(ValueModel):
    filesystem_read: Effect = Field(default_factory=Effect)
    filesystem_write: Effect = Field(default_factory=Effect)
    network: Effect = Field(default_factory=Effect)
    environment: Effect = Field(default_factory=Effect)
    subprocess: Effect = Field(default_factory=Effect)
    state_mutation: Effect = Field(default_factory=Effect)
    secrets: Effect = Field(default_factory=Effect)
    external_service: Effect = Field(default_factory=Effect)


class Availability(ValueModel):
    value: Literal["unconditional", "unknown"]
    evidence: Evidence


class Overload(ValueModel):
    source: SourceSpan
    signature: Signature
    evidence: Evidence = Evidence.DECLARED


class Capability(ValueModel):
    id: str
    name: str
    qualified_name: str
    kind: Literal["function"] = "function"
    source: SourceSpan
    docstring: str | None = None
    execution: ExecutionForm
    signature: Signature
    decorators: tuple[Expression, ...] = ()
    overloads: tuple[Overload, ...] = ()
    availability: Availability
    effects: Effects = Field(default_factory=Effects)
    evidence: Evidence = Evidence.OBSERVED

    @model_validator(mode="after")
    def consistent_identity(self) -> Self:
        if not (
            self.name == self.qualified_name == self.source.symbol
            and "." not in self.name
            and self.id == f"python:{self.source.module}:{self.qualified_name}"
        ):
            raise ValueError("Inconsistent module-level capability identity")
        if any(
            o.source.module != self.source.module or o.source.symbol != self.name
            for o in self.overloads
        ):
            raise ValueError("Overload source does not match capability")
        return self


class CapabilityDocument(ValueModel):
    schema_version: Literal["apizr.capability/v1"] = "apizr.capability/v1"
    source: Source
    capabilities: tuple[Capability, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()

    @field_validator("capabilities")
    @classmethod
    def ordered_unique(cls, values: tuple[Capability, ...]) -> tuple[Capability, ...]:
        if len({c.id for c in values}) != len(values):
            raise ValueError("Duplicate capability IDs")
        return tuple(sorted(values, key=lambda c: c.id))

    @field_validator("diagnostics")
    @classmethod
    def ordered_diagnostics(
        cls, values: tuple[Diagnostic, ...]
    ) -> tuple[Diagnostic, ...]:
        return tuple(
            sorted(values, key=lambda d: (d.source.line, d.code.value, d.message))
        )

    @model_validator(mode="after")
    def consistent_module(self) -> Self:
        spans = [c.source for c in self.capabilities] + [
            d.source for d in self.diagnostics
        ]
        if any(s.module != self.source.module for s in spans):
            raise ValueError("Source modules must match the document")
        return self

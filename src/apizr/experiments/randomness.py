"""Bounded lexical randomness evidence; presence never proves execution."""

import ast
import math
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, field_validator

from apizr.experiments._lexical import (
    MAX_DEPTH,
    MAX_SOURCE_BYTES,
    LexicalVisitor,
    SourceLimit,
    bounded_tree,
)
from apizr.experiments.model import (
    EvidenceOrigin,
    ExperimentValue,
    Name,
    RandomnessControl,
    Reference,
    ordered_evidence,
)

# An explicit import-to-distribution mapping, never an arbitrary package resolver.
_DISTRIBUTIONS = {
    "numpy": "numpy",
    "pandas": "pandas",
    "sklearn": "scikit-learn",
    "joblib": "joblib",
    "torch": "torch",
    "tensorflow": "tensorflow",
}
_APIS = {
    "random.seed": ("python.random", "seed", "a"),
    "numpy.random.seed": ("numpy", "random.seed", "seed"),
    "numpy.random.default_rng": ("numpy", "random.default_rng", "seed"),
    "torch.manual_seed": ("torch", "manual_seed", "seed"),
    "tensorflow.random.set_seed": ("tensorflow", "random.set_seed", "seed"),
}
_MODULES = frozenset(
    {"random", "numpy", "numpy.random", "torch", "tensorflow", "tensorflow.random"}
)
_REFERENCE = TypeAdapter[str](Reference)

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
        if any(item not in _DISTRIBUTIONS.values() for item in items):
            raise ValueError("randomness_distribution_invalid")
        return ordered_evidence(items, lambda item: item)


def _module(name: str) -> bool:
    return name in _MODULES or name == "sklearn" or name.startswith("sklearn.")


def _member(name: str) -> bool:
    return (
        name in _APIS
        or name in {"numpy.random", "tensorflow.random"}
        or name.startswith("sklearn.")
    )


def _literal(
    expression: ast.expr | None, provider: str, name: str
) -> tuple[int | float | str | None, RandomnessDiagnosticCode | None]:
    if expression is None:
        return None, "uncontrolled_randomness"
    value: object
    if isinstance(expression, ast.Constant):
        value = expression.value
    elif (
        isinstance(expression, ast.UnaryOp)
        and isinstance(expression.op, (ast.UAdd, ast.USub))
        and isinstance(expression.operand, ast.Constant)
        and type(expression.operand.value) in (int, float)
    ):
        number = expression.operand.value
        assert isinstance(number, (int, float))
        value = -number if isinstance(expression.op, ast.USub) else number
    else:
        return None, "dynamic_randomness_control"
    if value is None:
        return None, "uncontrolled_randomness"
    if type(value) is int and -(2**63) <= value < 2**63:
        if (
            provider == "sklearn" or (provider == "numpy" and name == "random.seed")
        ) and not 0 <= value < 2**32:
            return None, "unsupported_randomness_literal"
        if provider == "numpy" and value < 0:
            return None, "unsupported_randomness_literal"
        return value, None
    if provider == "python.random":
        if type(value) is float and math.isfinite(value):
            return value, None
        if isinstance(value, str):
            # The canonical finite-value validator also bounds/validates strings.
            return value, None
    return None, "unsupported_randomness_literal"


class _Discovery(LexicalVisitor):
    def __init__(self, source: str) -> None:
        super().__init__(_module, _member)
        self.source = source
        self.controls: dict[tuple[str, str], RandomnessControl] = {}
        self.diagnostics: list[RandomnessDiagnostic] = []

    def diagnostic(self, code: RandomnessDiagnosticCode, node: ast.Call) -> None:
        self.diagnostics.append(
            RandomnessDiagnostic(
                code=code, source=self.source, line=node.lineno, column=node.col_offset
            )
        )
        if len(self.diagnostics) > 512:
            raise SourceLimit(parsed=True)

    def record(self, control: RandomnessControl, node: ast.Call) -> None:
        key = (control.provider, control.name)
        previous = self.controls.get(key)
        # JSON equality distinguishes e.g. integer 1 from float 1.0.
        if (
            previous is not None
            and previous.model_dump_json() != control.model_dump_json()
        ):
            control = RandomnessControl(
                provider=control.provider,
                name=control.name,
                value=None,
                origin=EvidenceOrigin.UNKNOWN,
            )
            self.diagnostic("randomness_control_conflict", node)
        self.controls[key] = control
        if len(self.controls) > 128:
            raise SourceLimit(parsed=True)

    def visit_Call(self, node: ast.Call) -> None:
        qualified = self.resolve_call(node, max_attributes=MAX_DEPTH)
        if qualified in _APIS:
            provider, name, keyword = _APIS[qualified]
            values = list(node.args) + [
                item.value for item in node.keywords if item.arg == keyword
            ]
            unsupported = len(values) > 1 or any(
                item.arg != keyword for item in node.keywords
            )
            self.control(node, provider, name, values, unsupported)
        elif qualified.startswith("sklearn."):
            values = [
                item.value for item in node.keywords if item.arg == "random_state"
            ]
            if values:
                self.control(
                    node,
                    "sklearn",
                    qualified.removeprefix("sklearn.") + ".random_state",
                    values,
                    len(values) > 1 or any(item.arg is None for item in node.keywords),
                )
        self.generic_visit(node)

    def control(
        self,
        node: ast.Call,
        provider: str,
        name: str,
        values: list[ast.expr],
        unsupported: bool,
    ) -> None:
        value, code = (
            (None, "unsupported_randomness_arguments")
            if unsupported
            else _literal(values[0] if values else None, provider, name)
        )
        try:
            control = RandomnessControl(
                provider=provider,
                name=name,
                value=value,
                origin=EvidenceOrigin.UNKNOWN
                if value is None
                else EvidenceOrigin.STATIC,
            )
        except (ValueError, UnicodeError):
            # Names and literal values are untrusted source text, never echo them.
            try:
                control = RandomnessControl(
                    provider=provider,
                    name=name,
                    value=None,
                    origin=EvidenceOrigin.UNKNOWN,
                )
            except (ValueError, UnicodeError):
                self.diagnostic("randomness_control_name_invalid", node)
                return
            code = "unsupported_randomness_literal"
        if code is not None:
            self.diagnostic(code, node)
        self.record(control, node)
        if provider in {"torch", "tensorflow"}:
            self.record(
                RandomnessControl(
                    provider=provider,
                    name="accelerator_determinism",
                    value=None,
                    origin=EvidenceOrigin.UNKNOWN,
                ),
                node,
            )
            self.diagnostic("framework_determinism_unknown", node)


def discover_randomness(
    source: str | bytes, *, source_reference: str
) -> RandomnessResult:
    """Inspect supplied Python, never importing frameworks or running any code."""
    try:
        _REFERENCE.validate_python(source_reference, strict=True)
        tree = bounded_tree(source)
        discovery = _Discovery(source_reference)
        discovery.visit(tree)
    except SourceLimit as error:
        return RandomnessResult(
            diagnostics=(
                RandomnessDiagnostic(
                    code="randomness_discovery_limit",
                    source=source_reference if error.parsed else None,
                ),
            )
        )
    except (ValueError, UnicodeError, SyntaxError, RecursionError):
        return RandomnessResult(
            diagnostics=(RandomnessDiagnostic(code="randomness_source_invalid"),)
        )
    candidates: set[str] = set()
    for node in ast.walk(tree):
        imports: list[str] = []
        if isinstance(node, ast.Import):
            imports = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imports = [node.module or ""]
        for name in imports:
            candidate = _DISTRIBUTIONS.get(name.split(".")[0])
            if candidate is not None:
                candidates.add(candidate)
    return RandomnessResult(
        controls=tuple(discovery.controls.values()),
        diagnostics=tuple(discovery.diagnostics),
        relevant_distributions=tuple(sorted(candidates)),
    )

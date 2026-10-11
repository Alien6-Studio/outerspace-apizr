"""Bounded literal assignment candidates, without evaluating expressions."""

import ast
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, field_validator

from apizr.experiments._lexical import MAX_SOURCE_BYTES, SourceLimit, bounded_tree
from apizr.experiments.model import (
    EvidenceOrigin,
    ExperimentValue,
    Parameter,
    Reference,
)
from apizr.experiments.values import MAX_DEPTH, MAX_NODES

_REFERENCE = TypeAdapter[str](Reference)


class ParameterSignal(ExperimentValue):
    parameter: Parameter
    source: Reference
    line: Annotated[int, Field(ge=1, le=MAX_SOURCE_BYTES)]
    column: Annotated[int, Field(ge=0, le=MAX_SOURCE_BYTES)]

    @field_validator("parameter")
    @classmethod
    def static_only(cls, value: Parameter) -> Parameter:
        if value.origin != EvidenceOrigin.STATIC:
            raise ValueError("parameter_signal_origin")
        return value


class ParameterDiagnostic(ExperimentValue):
    code: Literal[
        "dynamic_parameter_value",
        "parameter_literal_invalid",
        "parameter_assignment_unsupported",
        "parameter_source_invalid",
        "parameter_discovery_limit",
    ]
    source: Reference | None = None
    line: Annotated[int, Field(ge=1, le=MAX_SOURCE_BYTES)] | None = None
    column: Annotated[int, Field(ge=0, le=MAX_SOURCE_BYTES)] | None = None


class ParameterDiscoveryResult(ExperimentValue):
    signals: Annotated[tuple[ParameterSignal, ...], Field(max_length=256)] = ()
    diagnostics: Annotated[tuple[ParameterDiagnostic, ...], Field(max_length=512)] = ()

    @field_validator("signals")
    @classmethod
    def ordered(
        cls, values: tuple[ParameterSignal, ...]
    ) -> tuple[ParameterSignal, ...]:
        keys = [(s.source, s.line, s.column, s.parameter.name) for s in values]
        if len(set(keys)) != len(keys):
            raise ValueError("parameter_duplicate_occurrence")
        return tuple(
            sorted(values, key=lambda s: (s.source, s.line, s.column, s.parameter.name))
        )

    @field_validator("diagnostics")
    @classmethod
    def diagnostics_ordered(
        cls, values: tuple[ParameterDiagnostic, ...]
    ) -> tuple[ParameterDiagnostic, ...]:
        return tuple(
            sorted(
                set(values),
                key=lambda d: (d.source or "", d.line or 0, d.column or 0, d.code),
            )
        )


class _Dynamic(ValueError):
    pass


def _literal(expression: ast.expr | None) -> object:
    remaining = MAX_NODES

    def visit(node: ast.expr | None, depth: int) -> object:
        nonlocal remaining
        remaining -= 1
        if depth > MAX_DEPTH or remaining < 0:
            raise ValueError("parameter_literal_limit")
        if isinstance(node, ast.Constant):
            return node.value
        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, (ast.UAdd, ast.USub))
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) in (int, float)
        ):
            value = node.operand.value
            assert isinstance(value, (int, float))
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [visit(child, depth + 1) for child in node.elts]
        if isinstance(node, ast.Dict):
            result: dict[str, object] = {}
            for key, value in zip(node.keys, node.values, strict=True):
                if (
                    not isinstance(key, ast.Constant)
                    or type(key.value) is not str
                    or key.value in result
                ):
                    raise ValueError("parameter_object_key")
                result[key.value] = visit(value, depth + 1)
            return result
        raise _Dynamic

    return visit(expression, 0)


def discover_parameters(
    source: str | bytes, *, source_reference: str
) -> ParameterDiscoveryResult:
    """Only direct module assignments; no propagation, nested scopes or call signatures."""
    try:
        _REFERENCE.validate_python(source_reference, strict=True)
        tree = bounded_tree(source)
    except SourceLimit:
        return ParameterDiscoveryResult(
            diagnostics=(ParameterDiagnostic(code="parameter_discovery_limit"),)
        )
    except (ValueError, SyntaxError, UnicodeError, RecursionError, TypeError):
        return ParameterDiscoveryResult(
            diagnostics=(ParameterDiagnostic(code="parameter_source_invalid"),)
        )
    signals: list[ParameterSignal] = []
    diagnostics: list[ParameterDiagnostic] = []
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        targets = (
            statement.targets
            if isinstance(statement, ast.Assign)
            else [statement.target]
        )
        for target in targets:
            code: Literal[
                "dynamic_parameter_value",
                "parameter_literal_invalid",
                "parameter_assignment_unsupported",
            ]
            if not isinstance(target, ast.Name):
                code = "parameter_assignment_unsupported"
            else:
                try:
                    parameter = Parameter.model_validate(
                        {
                            "name": target.id,
                            "value": _literal(statement.value),
                            "origin": EvidenceOrigin.STATIC,
                        }
                    )
                    signals.append(
                        ParameterSignal(
                            parameter=parameter,
                            source=source_reference,
                            line=target.lineno,
                            column=target.col_offset,
                        )
                    )
                    continue
                except _Dynamic:
                    code = "dynamic_parameter_value"
                except (ValueError, UnicodeError):
                    code = "parameter_literal_invalid"
            diagnostics.append(
                ParameterDiagnostic(
                    code=code,
                    source=source_reference,
                    line=target.lineno,
                    column=target.col_offset,
                )
            )
        if len(signals) > 256 or len(diagnostics) > 512:
            return ParameterDiscoveryResult(
                diagnostics=(
                    ParameterDiagnostic(
                        code="parameter_discovery_limit", source=source_reference
                    ),
                )
            )
    return ParameterDiscoveryResult(
        signals=tuple(signals), diagnostics=tuple(diagnostics)
    )

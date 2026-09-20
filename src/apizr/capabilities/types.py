"""Framework-independent value types; expressions describe syntax, never objects."""

import ast
import keyword
import unicodedata
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ValueModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Evidence(str, Enum):
    DECLARED = "declared"
    OBSERVED = "observed"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class TypeForm(str, Enum):
    NAME = "name"
    ATTRIBUTE = "attribute"
    SUBSCRIPT = "subscript"
    UNION = "union"
    FORWARD_REFERENCE = "forward_reference"
    LITERAL = "literal"
    UNKNOWN = "unknown"


class DeclaredType(ValueModel):
    declared: str
    form: TypeForm
    evidence: Evidence = Evidence.DECLARED


class Expression(ValueModel):
    declared: str
    evidence: Evidence = Evidence.DECLARED


def logical_module(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    if not all(
        part.isidentifier() and not keyword.iskeyword(part)
        for part in normalized.split(".")
    ):
        raise ValueError("Expected a logical dotted Python module name")
    return normalized


def declared_type(node: ast.expr) -> DeclaredType:
    """Classify syntax while retaining the entire normalized declaration."""
    form = TypeForm.UNKNOWN
    if isinstance(node, ast.Name):
        form = TypeForm.NAME
    elif isinstance(node, ast.Attribute):
        form = TypeForm.ATTRIBUTE
    elif isinstance(node, ast.Subscript):
        form = TypeForm.SUBSCRIPT
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        form = TypeForm.UNION
    elif isinstance(node, ast.Constant):
        form = (
            TypeForm.FORWARD_REFERENCE
            if isinstance(node.value, str)
            else TypeForm.LITERAL
        )
    return DeclaredType(declared=ast.unparse(node), form=form)

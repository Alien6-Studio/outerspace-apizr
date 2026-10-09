"""Transport-neutral JSON inputs and callable invocation contracts."""

from typing import Literal

from apizr.capabilities.model import ParameterKind
from apizr.capabilities.types import ValueModel
from apizr.contract_types import Scalar as Scalar
from apizr.contract_types import TypeSpec


class Input(ValueModel):
    name: str
    kind: ParameterKind
    required: bool
    type: TypeSpec


class InvocationContract(ValueModel):
    capability_id: str
    name: str
    execution: Literal["sync", "async"]
    parameters: tuple[Input, ...]
    returns: TypeSpec
    description: str | None = None

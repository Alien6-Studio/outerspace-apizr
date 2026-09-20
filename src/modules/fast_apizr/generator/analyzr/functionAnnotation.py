import sys
from typing import ForwardRef, List, Optional, Union

from pydantic import BaseModel


class FunctionAnnotation(BaseModel):
    """Represents a Python type annotation, considering potentially nested types.

    This model captures details about a Python type annotation, including the general
    type and any nested or container types. The use of ForwardRef allows for the representation
    of nested types using circular references.
    """

    type: str = "any"  # The general type of the annotation (default is "any").
    of: Optional[
        List[Union[str, "FunctionAnnotation"]]
    ] = []  # Optional list representing the nested type(s).


if sys.version_info >= (3, 11):
    FunctionAnnotation.model_rebuild()
else:
    FunctionAnnotation.update_forward_refs()

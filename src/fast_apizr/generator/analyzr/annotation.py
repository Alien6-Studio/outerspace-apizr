from pydantic import BaseModel, validator

from typing import List, ForwardRef, Optional, Union

Annotation = ForwardRef("Annotation")


class Annotation(BaseModel):
    """Represents a Python type annotation, considering potentially nested types.

    This model captures details about a Python type annotation, including the general
    type and any nested or container types. The use of ForwardRef allows for the representation
    of nested types using circular references.
    """

    type: str = "any"  # The general type of the annotation (default is "any").
    of: Optional[
        List[Union[str, Annotation]]
    ] = []  # Optional list representing the nested type(s).

    @validator("of", pre=True, each_item=True)
    def check_of(cls, item):
        if isinstance(item, str):
            return {"type": item}
        return item


Annotation.model_rebuild()

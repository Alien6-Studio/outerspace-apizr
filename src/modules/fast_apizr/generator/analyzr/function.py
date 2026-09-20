from typing import List, Optional

from pydantic import BaseModel, Field

from .argument import Argument
from .functionAnnotation import FunctionAnnotation


class Function(BaseModel):
    name: str
    args: List[Argument] = Field(default_factory=list)
    returns: Optional[FunctionAnnotation] = None
    selected: bool = False
    is_async: bool = False

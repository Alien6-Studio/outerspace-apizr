from pydantic import BaseModel
from typing import List, Optional
from .argument import Argument
from .functionAnnotation import FunctionAnnotation


class Function(BaseModel):
    """Represents a function with its name, arguments, return type, and selection status.

    This model captures details about a function, including its name, the list of
    arguments, the return type (if specified), and a flag indicating whether the
    function is selected for further processing or not.
    """

    name: str  # The name of the function.
    args: List[Argument] = []  # List of arguments for the function.
    returns: Optional[FunctionAnnotation]  # The return type of the function.
    selected: bool = False  # Indicator to determine if the function is selected.

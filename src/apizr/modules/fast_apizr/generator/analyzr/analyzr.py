from typing import List, Tuple

from pydantic import BaseModel

from apizr.compat import DEFAULT_PYTHON

from .function import Function
from .importFrom import ImportFrom
from .imports import Import


class Analyzr(BaseModel):
    """Represents a structured analysis of a given code.

    This model is used to capture details about the functions, direct imports,
    and import-from statements in the code being analyzed. It serves as a
    foundation for generating FastAPI specific code or any other related tasks.
    """

    version: Tuple[int, int] = DEFAULT_PYTHON
    functions: List[Function]  # List of functions present in the analyzed code.
    imports: List[Import] = []  # Direct imports present in the analyzed code.
    imports_from: List[
        ImportFrom
    ] = []  # Import-from statements present in the analyzed code.

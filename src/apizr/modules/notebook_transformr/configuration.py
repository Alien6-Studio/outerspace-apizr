from typing import Tuple

from pydantic import BaseModel

from apizr.compat import DEFAULT_PYTHON


class NotebookTransformrConfiguration(BaseModel):
    python_version: Tuple[int, int] = DEFAULT_PYTHON
    encoding: str = "utf-8"

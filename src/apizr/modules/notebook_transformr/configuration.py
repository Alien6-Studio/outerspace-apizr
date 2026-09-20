from pydantic import BaseModel

from apizr.runtime import DEFAULT_PYTHON, PythonTarget


class NotebookTransformrConfiguration(BaseModel):
    python_version: PythonTarget = DEFAULT_PYTHON
    encoding: str = "utf-8"

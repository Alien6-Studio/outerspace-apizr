from pydantic import BaseModel

from apizr.runtime import DEFAULT_PYTHON, PythonTarget


class FastApizrConfiguration(BaseModel):
    python_version: PythonTarget = DEFAULT_PYTHON
    encoding: str = "utf-8"
    module_name: str = "main"
    api_filename: str = "app.py"

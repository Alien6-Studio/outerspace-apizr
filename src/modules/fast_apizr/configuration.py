from typing import Tuple

from pydantic import BaseModel

from src.compat import DEFAULT_PYTHON


class FastApizrConfiguration(BaseModel):
    python_version: Tuple[int, int] = DEFAULT_PYTHON
    encoding: str = "utf-8"
    module_name: str = "main"
    api_filename: str = "app.py"

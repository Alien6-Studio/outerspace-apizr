from typing import List, Optional

from pydantic import BaseModel, Field

from apizr.runtime import DEFAULT_PYTHON, PythonTarget


class KeywordConfig(BaseModel):
    version: str
    values: List[str]


class CodeAnalyzrConfiguration(BaseModel):
    python_version: PythonTarget = DEFAULT_PYTHON
    encoding: str = "utf-8"
    functions_to_analyze: Optional[str] = None
    ignore: Optional[str] = None
    keywords: List[KeywordConfig] = Field(default_factory=list)

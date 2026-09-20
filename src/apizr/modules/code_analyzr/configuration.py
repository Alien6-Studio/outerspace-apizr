from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from apizr.compat import DEFAULT_PYTHON


class KeywordConfig(BaseModel):
    version: str
    values: List[str]


class CodeAnalyzrConfiguration(BaseModel):
    python_version: Tuple[int, int] = DEFAULT_PYTHON
    encoding: str = "utf-8"
    functions_to_analyze: Optional[str] = None
    ignore: Optional[str] = None
    keywords: List[KeywordConfig] = Field(default_factory=list)

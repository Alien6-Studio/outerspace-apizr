from typing import Literal

from pydantic import BaseModel

from .annotation import Annotation


class Argument(BaseModel):
    name: str
    annotation: Annotation
    kind: Literal["positional_only", "positional_or_keyword", "keyword_only"] = (
        "positional_or_keyword"
    )
    has_default: bool = False

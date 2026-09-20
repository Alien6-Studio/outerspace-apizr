from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel, Field


class Annotation(BaseModel):
    type: str = "any"
    of: Optional[List[Union[str, "Annotation"]]] = Field(default_factory=list)


Annotation.model_rebuild()

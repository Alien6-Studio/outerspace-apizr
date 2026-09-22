from pydantic import BaseModel, Field, StrictStr, field_validator

from apizr.runtime import DEFAULT_PYTHON, PythonTarget


class NotebookTransformrConfiguration(BaseModel):
    python_version: PythonTarget = DEFAULT_PYTHON
    encoding: str = "utf-8"
    include_tags: list[StrictStr] = Field(default_factory=list)
    exclude_tags: list[StrictStr] = Field(default_factory=list)

    @field_validator("include_tags", "exclude_tags")
    @classmethod
    def valid_tags(cls, values):
        if any(not value.strip() or value != value.strip() for value in values):
            raise ValueError(
                "Cell tags must be nonempty strings without surrounding whitespace"
            )
        if len(values) != len(set(values)):
            raise ValueError("Cell tags must be unique")
        return values

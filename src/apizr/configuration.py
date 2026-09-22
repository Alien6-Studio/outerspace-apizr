"""Validated configuration shared by the CLI and HTTP interfaces."""

from pydantic import BaseModel, Field, JsonValue, StrictStr

from apizr.runtime import DEFAULT_PYTHON, PythonTarget, validate_python_target

from .modules.code_analyzr.configuration import CodeAnalyzrConfiguration
from .modules.dockerizr.configuration import DockerizrConfiguration
from .modules.fast_apizr.configuration import FastApizrConfiguration
from .modules.notebook_transformr.configuration import NotebookTransformrConfiguration


class MainConfiguration(BaseModel):
    python_version: PythonTarget = DEFAULT_PYTHON
    encoding: str = "utf-8"
    notebook_transformr: NotebookTransformrConfiguration = Field(
        default_factory=NotebookTransformrConfiguration
    )
    code_analyzr: CodeAnalyzrConfiguration = Field(
        default_factory=CodeAnalyzrConfiguration
    )
    fast_apizr: FastApizrConfiguration = Field(default_factory=FastApizrConfiguration)
    dockerizr: DockerizrConfiguration = Field(default_factory=DockerizrConfiguration)
    requirements: StrictStr | None = None
    include: list[StrictStr] = Field(default_factory=list)
    plugin_options: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)

    def dispatch(self):
        validate_python_target(self.python_version)
        if self.python_version > DEFAULT_PYTHON:
            raise ValueError(
                "Run Apizr with a Python version at least as recent as the requested target"
            )
        for config in (
            self.notebook_transformr,
            self.code_analyzr,
            self.fast_apizr,
            self.dockerizr,
        ):
            config.python_version = self.python_version
            config.encoding = self.encoding

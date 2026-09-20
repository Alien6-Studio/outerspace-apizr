"""Validated configuration shared by the CLI and HTTP interfaces."""

from typing import Tuple

from pydantic import BaseModel, Field

from apizr.compat import DEFAULT_PYTHON

from .modules.code_analyzr.configuration import CodeAnalyzrConfiguration
from .modules.dockerizr.configuration import DockerizrConfiguration
from .modules.fast_apizr.configuration import FastApizrConfiguration
from .modules.notebook_transformr.configuration import NotebookTransformrConfiguration


class MainConfiguration(BaseModel):
    python_version: Tuple[int, int] = DEFAULT_PYTHON
    encoding: str = "utf-8"
    notebook_transformr: NotebookTransformrConfiguration = Field(
        default_factory=NotebookTransformrConfiguration
    )
    code_analyzr: CodeAnalyzrConfiguration = Field(
        default_factory=CodeAnalyzrConfiguration
    )
    fast_apizr: FastApizrConfiguration = Field(default_factory=FastApizrConfiguration)
    dockerizr: DockerizrConfiguration = Field(default_factory=DockerizrConfiguration)

    def dispatch(self):
        if not (3, 8) <= self.python_version <= (3, 14):
            raise ValueError("Supported Python targets are 3.8 through 3.14")
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

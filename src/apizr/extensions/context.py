from enum import Enum, auto
from pathlib import Path
from typing import Optional, Protocol


class EncodingConfiguration(Protocol):
    encoding: str


class ContextStatus(Enum):
    PENDING = auto()
    SUCCESS = auto()
    FAILED = auto()
    PROGRESS = auto()


class ContextException(RuntimeError):
    pass


class Context:
    """State passed explicitly between pipeline stages."""

    def __init__(self):
        self.config: Optional[EncodingConfiguration] = None
        self.data = {}
        self._result = {}
        self.input_path = None
        self.source_dir = None
        self.output_dir = None
        self.requirements_path = None
        self.lang = "en"
        self.prompt = False
        self.status = ContextStatus.PENDING
        self._logs = []

    @property
    def result(self):
        return self._result

    @result.setter
    def result(self, value):
        if isinstance(value, dict):
            self._result.update(value)
        else:
            key, content = value
            self._result[key] = content

    def add_log(self, message, level="info"):
        self._logs.append(f"[{level.upper()}] {message}")

    def read_input(self):
        if self.input_path is None:
            raise ContextException("Input path is not set")
        if self.config is None:
            raise ContextException("Configuration is not set")
        self.data = self.input_path.read_text(encoding=self.config.encoding)
        return self

    def write_output(self, key, path=None):
        if self.output_dir is None:
            raise ContextException("Output directory is not set")
        target = self.output_dir / (path or "output.txt")
        if not target.resolve().is_relative_to(self.output_dir.resolve()):
            raise ContextException("Output path must stay inside the output directory")
        if self.config is None:
            raise ContextException("Configuration is not set")
        target.write_text(self._result[key], encoding=self.config.encoding)
        return Path(target)

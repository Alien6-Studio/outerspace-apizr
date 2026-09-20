import logging

from enum import Enum, auto
from pathlib import Path
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)
logger = logging.getLogger(__name__)

class ContextStatus(Enum):
    PENDING = auto()
    SUCCESS = auto()
    FAILED = auto()
    PROGRESS = auto()

class ContextException(Exception):
    """Custom exception for Context-related errors."""
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class Context:
    def __init__(self):
        """
        A class that stores data shared across steps.
        
        Results are stored in the result attribute as a tuple of (key, value).
        """
        self._config: BaseModel = None
        self._logs: List[str] = []
        self._data: Optional[Any] = None
        self._result: Dict[str, str] = {}  
        self._input_path: Optional[Path] = None
        self._output_dir: Optional[Path] = None
        self._lang: Optional[str] = None
        self._prompt: bool = True
        self._status: ContextStatus = ContextStatus.PENDING

    @property
    def config(self):
        return self._config

    @config.setter
    def config(self, value):
        self._config = value

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value

    @property
    def result(self) -> Dict[str, str]:
        return self._result

    @result.setter
    def result(self, value: Dict[str, str]):
        key, value = value
        self._result[key] = value

    @property
    def input_path(self):
        return self._input_path

    @input_path.setter
    def input_path(self, value):
        self._input_path = value    

    @property
    def output_dir(self):
        return self._output_dir

    @output_dir.setter
    def output_dir(self, value):
        self._output_dir = value

    @property
    def lang(self):
        return self._lang

    @lang.setter
    def lang(self, value):
        self._lang = value

    @property
    def prompt(self):
        return self._prompt
    
    @prompt.setter
    def prompt(self, value):
        self._prompt = value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    def add_log(self, message: str, level: str = 'info'):
        """Add a log message to the context logs."""
        log_entry = f"[{level.upper()}] {message}"
        self._logs.append(log_entry)

    def read_input(self):
        """
        Reads data from the input path and stores it in the data attribute.
        """
        if not self._input_path:
            self.add_log("Failed to read input: Input path is not set.")
            raise ContextException("Input path is not set.")
        
        try:
            with open(self._input_path, 'r') as file:
                self._data = file.read()
            self.add_log(f"Data read successfully from {self._input_path}.")
        except Exception as e:
            self.add_log(f"Failed to read from {self._input_path}: {str(e)}")
            raise ContextException(f"Error reading from {self._input_path}: {str(e)}") from e

    def write_output(self, key: str, path: Path = None):
        """
        Writes the result to the output path (output_dir / output_filename)
        """
        if not self._output_dir:
            self.add_log("Failed to write output: Output dir is not set.")
            raise ContextException("Output dir is not set.")
        
        output_path = self._output_dir / path if path else self._output_dir / "output.txt"

        try:

            with open(output_path, 'w') as file:
                file.write(self._result[key])
            self.add_log(f"Data written successfully to {output_path}.")
        except Exception as e:
            self.add_log(f"Failed to write to {output_path}: {str(e)}")
            raise ContextException(f"Error writing to {output_path}: {str(e)}") from e
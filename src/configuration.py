from pydantic import BaseModel

from modules.code_analyzr.configuration import CodeAnalyzrConfiguration
from modules.dockerizr.configuration import DockerizrConfiguration, GunicornConfiguration
from modules.fast_apizr.configuration import FastApizrConfiguration
from modules.notebook_transformr.configuration import NotebookTransformrConfiguration


class MainConfiguration(BaseModel):
    """
    Main configuration class that encapsulates configurations for multiple modules.

    This configuration class is designed to simplify the initialization process by allowing
    the user to provide `python_version` and `encoding` once. These values are then propagated
    to each of the sub-configurations.

    Attributes:
    - python_version (str): The Python version to be used. Must match the pattern "3.11".
    - encoding (str): The character encoding format. Must be "utf-8".
    - notebook_transformr (NotebookTransformrConfiguration): Configuration for the NotebookTransformr module.
    - code_analyser (CodeAnalyzrConfiguration): Configuration for the CodeAnalyzr module.
    - fast_apizr (FastApizrConfiguration): Configuration for the FastApizr module.
    - dockerizr (DockerizrConfiguration): Configuration for the Dockerizr module.

    Usage:
    ```python
    config = MainConfiguration(python_version="3.11", encoding="utf-8",
                        notebook_transformr={...},
                        code_analyser={...},
                        fast_apizr={...},
                        dockerizr={...})
    ```

    Note:
    The `python_version` and `encoding` values are automatically passed to each sub-configuration.
    """

    python_version: tuple = (3, 8)
    encoding: str = "utf-8"
    notebook_transformr: NotebookTransformrConfiguration = NotebookTransformrConfiguration()
    code_analyzr: CodeAnalyzrConfiguration = CodeAnalyzrConfiguration()
    fast_apizr: FastApizrConfiguration = FastApizrConfiguration()
    dockerizr: DockerizrConfiguration = DockerizrConfiguration()

    def __init__(self, **data):
        super().__init__(**data)

    def dispatch(self):
        """
        Dispatches the `python_version` and `encoding` values to each sub-configuration.
        """

        self.notebook_transformr.python_version = self.python_version
        self.notebook_transformr.encoding = self.encoding

        self.code_analyzr.python_version = self.python_version
        self.code_analyzr.encoding = self.encoding

        self.fast_apizr.python_version = self.python_version
        self.fast_apizr.encoding = self.encoding

        self.dockerizr.python_version = self.python_version
        self.dockerizr.encoding = self.encoding
        self.dockerizr.api_filename = self.fast_apizr.api_filename

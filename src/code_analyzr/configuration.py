from typing import List, Optional

from pydantic import BaseModel


class KeywordConfig(BaseModel):
    """
    Configuration for specific Python version keywords.

    Attributes:
    - version (str): The Python version for which the keywords are relevant.
    - values (List[str]): List of keywords for the specified Python version.
    """

    version: str
    values: List[str]


class CodeAnalyzrConfiguration(BaseModel):
    """
    Configuration settings for the CodeAnalyzr module.

    This configuration provides settings related to the analysis of Python code.

    Attributes:
    - python_version (str): The Python version to be used for the analysis. Default is "3.8".
    - encoding (str): The character encoding format for reading and writing files. Default is "utf-8".
    - functions_to_analyze (Optional[str]): Specific functions to be analyzed. If not provided, all functions will be considered.
    - ignore (Optional[str]): Functions or patterns to be ignored during the analysis.
    - keywords (List[KeywordConfig]): List of keyword configurations, each specifying keywords for a particular Python version.

    Example:
    ```python
    config = CodeAnalyzrConfiguration(
        functions_to_analyze="my_function",
        ignore="helper_function",
        keywords=[{"version": "3.10", "values": ["match", "case"]}]
    )
    print(config.functions_to_analyze)  # Outputs: "my_function"
    ```

    Note:
    If not provided, the default values for `python_version` and `encoding` will be used.
    """

    python_version: tuple = (3, 8)
    encoding: str = "utf-8"
    functions_to_analyze: Optional[str] = None
    ignore: Optional[str] = None
    keywords: List[KeywordConfig] = [{"version": "3.10", "values": ["match", "case"]}]

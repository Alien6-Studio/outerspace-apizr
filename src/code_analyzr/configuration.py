from typing import Any, Dict, List, Optional

from pydantic import BaseModel, validator


class KeywordConfig(BaseModel):
    """
    Configuration for specific Python version keywords.

    Attributes:
    - version (str): The Python version for which the keywords are relevant.
    - values (List[str]): List of keywords for the specified Python version.
    """

    version: str
    values: List[str]

    # Ensure that version is in the correct format (e.g., "3.10")
    @validator("version")
    def validate_version_format(cls, v):
        if not all(part.isdigit() for part in v.split(".")):
            raise ValueError("Invalid version format!")
        return v


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

    # Ensure that keywords is a list of KeywordConfig objects
    @validator("keywords", pre=True, each_item=True)
    def validate_keywords(cls, v):
        if not isinstance(v, Dict) or "version" not in v or "values" not in v:
            raise ValueError(
                "Each keyword entry must be a dictionary with 'version' and 'values' keys."
            )
        return v

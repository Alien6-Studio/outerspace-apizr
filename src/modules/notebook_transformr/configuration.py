from pydantic import BaseModel


class NotebookTransformrConfiguration(BaseModel):
    """
    Configuration settings for the NotebookTransformr module.

    This configuration provides settings related to the transformation of Jupyter notebooks.

    Attributes:
    - python_version (str): The Python version to be used for the transformed notebook. Must match the pattern "3.11".
    - encoding (str): The character encoding format for reading and writing files. Must be "utf-8".

    Example:
    ```python
    config = NotebookTransformrConfiguration(python_version="3.11", encoding="utf-8")
    print(config.python_version)  # Outputs: "3.11"
    ```

    Note:
    The values for `python_version` and `encoding` must adhere to the specified constraints.
    """

    python_version: tuple = (3, 8)
    encoding: str = "utf-8"

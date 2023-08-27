from pydantic import BaseModel

HOSTNAME = "0.0.0.0"  # nosec B104


class FastApizrConfiguration(BaseModel):
    """Defines the configuration for generating the FastAPI application.

    Attributes:
        python_version (str): The Python version to be used. Defaults to "3.8".
        encoding (str): The character encoding format for reading and writing files. Defaults to "utf-8".
        module_name (str): The name of the module. Defaults to "main".
        api_filename (str): The name of the generated file. Defaults to "app.py".
    """

    python_version: tuple = (3, 8)
    encoding: str = "utf-8"
    module_name: str = "main"
    api_filename: str = "app.py"

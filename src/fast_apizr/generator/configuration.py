from pydantic import BaseModel


class Configuration(BaseModel):
    """Defines the configuration for generating the FastAPI application.

    Attributes:
        module_name (str): The name of the module. Defaults to "main".
        host (str): The host on which the application will run. Defaults to "0.0.0.0".
        port (int): The port on which the application will run. Defaults to 5000.
        debug (bool): Whether to enable debugging mode. Defaults to False.
        api_filename (str): The name of the generated file. Defaults to "app.py".
    """

    module_name: str = "main"
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False
    api_filename: str = "app.py"

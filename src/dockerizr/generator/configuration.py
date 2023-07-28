from pydantic import BaseModel
from typing import Tuple


class ProjectConfig(BaseModel):
    """Defines the configuration related to the overall project structure.

    Attributes:
        project_path (str): Path to the project directory. Defaults to "." (current directory).
        main_folder (str): Name of the main folder. Defaults to an empty string.
        main_file (str): Name of the main file of the project. Defaults to "main.py".
        main_module (str): Name of the main module. Defaults to "main".
        home_path (str): Path to the home directory. Defaults to an empty string.
        encoding (str): Character encoding used in the project. Defaults to an empty string.
        python_version (Tuple[int, int]): Version of Python used. Defaults to (3, 8).
    """

    project_path: str = "."
    main_folder: str = ""
    main_file: str = "main.py"
    main_module: str = "main"
    home_path: str = ""
    encoding: str = ""
    python_version: Tuple[int, int] = (3, 8)


class ApizerConfig(BaseModel):
    """Defines the configuration related to the API generation framework.

    Attributes:
        framework (str): Name of the API framework. Defaults to "fastAPI".
        pref_func (str): Preferred function name. Defaults to an empty string.
        api_file_name (str): Name of the API file. Defaults to "app.py".
        debug (bool): Whether to enable debugging mode for the API. Defaults to True.
    """

    framework: str = "fastAPI"
    pref_func: str = ""
    api_file_name: str = "app.py"
    debug: bool = True


class ServerConfig(BaseModel):
    """Defines the configuration for the server that will run the application.

    Attributes:
        server_app (str): Server application name. Defaults to "gunicorn".
        wsgi_file_name (str): Name of the WSGI file. Defaults to "wsgi.py".
        wsgi_conf_file_name (str): Name of the WSGI configuration file. Defaults to "gunicorn.conf.py".
        host (str): Host address for the server. Defaults to "0.0.0.0".
        port (int): Port number for the server. Defaults to 5001.
        nb_workers (int): Number of workers for the server. Defaults to 2.
    """

    server_app: str = "gunicorn"
    wsgi_file_name: str = "wsgi.py"
    wsgi_conf_file_name: str = "gunicorn.conf.py"
    host: str = "0.0.0.0"
    port: int = 5001
    nb_workers: int = 2


class Configuration(BaseModel):
    """Aggregates the configurations for the project, API, and server.

    Attributes:
        project (ProjectConfig): Configuration for the overall project structure.
        apizer (ApizerConfig): Configuration related to the API generation framework.
        server (ServerConfig): Configuration for the server.
    """

    project: ProjectConfig
    apizer: ApizerConfig
    server: ServerConfig

from typing import List, Optional

from pydantic import BaseModel

HOSTNAME = "0.0.0.0"  # nosec B104


class Dependency(BaseModel):
    """
    Configuration for a specific dependency.

    Attributes:
    - name (str): Name of the dependency.
    - packages (List[str]): List of packages associated with the dependency.
    """

    name: str
    packages: List[str]


class GunicornConfiguration(BaseModel):
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
    host: str = HOSTNAME
    port: int = 5001
    workers: int = 2
    timeout: int = 60


class DockerizrConfiguration(BaseModel):
    """
    Configuration settings for the Dockerizr module.

    This configuration provides settings related to the Docker containerization of the application.

    Attributes:
    - python_version (str): The Python version to be used. Defaults to "3.8".
    - encoding (str): The character encoding format for reading and writing files. Defaults to "utf-8".
    - api_filename (str): Name of the FastAPI generated file. Defaults to "app.py".
    - project_path (str): Path to the project directory. Defaults to the current directory.
    - main_folder (str): Name of the main folder for the project.
    - server (GunicornConfiguration): Configuration settings for the Gunicorn server.
    """

    python_version: tuple = (3, 8)
    encoding: str = "utf-8"
    docker_image: str = "alpine"
    docker_image_tag: str = "alpine3.18"
    dependencies: List[Dependency] = [
        {
            "name": "numpy",
            "packages": ["gcc", "g++", "musl-dev", "python3-dev", "gfortran"],
        },
        {
            "name": "scikit_learn",
            "packages": [
                "gcc",
                "g++",
                "musl-dev",
                "python3-dev",
                "gfortran",
                "openblas-dev",
                "lapack-dev",
            ],
        },
    ]
    custom_packages: List[str] = []
    project_path: str = "."
    api_filename: str = "app.py"
    module_name: Optional[str] = "main"
    server: GunicornConfiguration = GunicornConfiguration()
    apizr_requirements: List[str] = [
        "gunicorn==21.2.0",
        "uvicorn[standard]",
    ]
    entrypoint: Optional[str] = ""

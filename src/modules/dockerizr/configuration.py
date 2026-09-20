from typing import List, Literal, Tuple

from pydantic import BaseModel, Field

from src.compat import DEFAULT_PYTHON

HOSTNAME = "0.0.0.0"


class Dependency(BaseModel):
    name: str
    packages: List[str]


class GunicornConfiguration(BaseModel):
    server_app: str = "gunicorn"
    wsgi_file_name: str = "wsgi.py"
    wsgi_conf_file_name: str = "gunicorn.conf.py"
    host: str = HOSTNAME
    port: int = Field(default=5001, ge=1, le=65535)
    workers: int = Field(default=1, ge=1)
    timeout: int = Field(default=60, ge=1)


class DockerizrConfiguration(BaseModel):
    python_version: Tuple[int, int] = DEFAULT_PYTHON
    encoding: str = "utf-8"
    docker_image: Literal["alpine", "debian"] = "debian"
    docker_image_tag: str = "slim"
    dependencies: List[Dependency] = Field(default_factory=list)
    custom_packages: List[str] = Field(default_factory=list)
    project_path: str = "."
    api_filename: str = "app.py"
    module_name: str = "app"
    server: GunicornConfiguration = Field(default_factory=GunicornConfiguration)
    apizr_requirements: List[str] = Field(
        default_factory=lambda: [
            "fastapi>=0.115,<1",
            "pydantic>=2.10,<3",
            "typing-extensions>=4.12,<5",
            "uvicorn[standard]>=0.30,<1",
        ]
    )
    entrypoint: str = ""

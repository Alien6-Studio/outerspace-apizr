import logging
from os import path
from jinja2 import Template

from .configuration import Configuration
from .errorLogger import LogError


class DockerfileGenerator:
    def __init__(self, conf: Configuration):
        self.conf = conf

    @LogError(logging)
    def generate_dockerfile(self):
        home_path = path.join(
            self.conf.project.project_path, self.conf.project.main_folder
        )
        with open(path.join(home_path, "Dockerfile"), "w") as f:
            f.write(self.dockerfile_generator())

    @LogError(logging)
    def dockerfile_generator(self) -> str:
        with open(
            path.join(path.dirname(__file__), "templates/Dockerfile.jinja"), "r"
        ) as f:
            template = Template(f.read())
            output = template.render(
                python_version=f"{self.conf.project.python_version[0]}.{self.conf.project.python_version[1]}",
                host=self.conf.server.host,
                port=self.conf.server.port,
            )
            return output

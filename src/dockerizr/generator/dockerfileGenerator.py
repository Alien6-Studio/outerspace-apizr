import logging
from os import path

from jinja2 import Template

from configuration import DockerizrConfiguration

from .errorLogger import LogError


class DockerfileGenerator:
    def __init__(self, conf: DockerizrConfiguration):
        self.conf = conf
        self.home_path = path.join(self.conf.project_path, self.conf.main_folder)

    @LogError(logging)
    def is_dependency_present(self, dependency_name: str) -> bool:
        return any(dep["name"]== dependency_name for dep in self.conf.dependencies)

    @LogError(logging)
    def get_dependency(self, dependency_name: str):
        for dep in self.conf.dependencies:
            if dep["name"] == dependency_name:
                return dep
        return None

    @LogError(logging)
    def get_alpine_packages(self) -> list:
        packages = []
        with open(path.join(self.home_path, "requirements.txt"), "r") as f:
            for line in f:
                library = line.strip().split("==")[0]
                if self.is_dependency_present(library):
                    packages.extend(self.get_dependency(library).packages)
        return list(set(packages))

    @LogError(logging)
    def generate_dockerfile(self):
        with open(path.join(self.home_path, "Dockerfile"), "w") as f:
            f.write(self.dockerfile_generator())

    @LogError(logging)
    def dockerfile_generator(self) -> str:
        with open(
            path.join(
                path.dirname(__file__),
                f"templates/dockerfile-{self.conf.docker_image}.jinja",
            ),
            "r",
        ) as f:
            template = Template(f.read())
            output = template.render(
                python_version=".".join(map(str, self.conf.python_version)),
                docker_image_tag=f"{self.conf.docker_image_tag}",
                host=self.conf.server.host,
                port=self.conf.server.port,
                dependencies=self.get_alpine_packages(),
            )
            return output

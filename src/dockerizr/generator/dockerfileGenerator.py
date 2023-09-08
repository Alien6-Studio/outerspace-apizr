import logging
import shutil
from os import path

from jinja2 import Template

from configuration import DockerizrConfiguration

from .errorLogger import LogError


class DockerfileGenerator:
    def __init__(self, conf: DockerizrConfiguration):
        self.conf = conf
        self.home_path = self.conf.project_path

    @LogError(logging)
    def is_dependency_present(self, dependency_name: str) -> bool:
        if not isinstance(self.conf.dependencies, list):
            logging.error("self.conf.dependencies is not a list.")
            return False

        for dep in self.conf.dependencies:
            if not isinstance(dep, dict):
                logging.error(f"Unexpected type in self.conf.dependencies: {type(dep)}")
                continue

            if "name" not in dep:
                logging.error("Missing 'name' key in dependency entry.")
                continue

            if dep["name"] == dependency_name:
                return True
        return False

    @LogError(logging)
    def get_dependency(self, dependency_name: str):
        for dep in self.conf.dependencies:
            if dep["name"] == dependency_name:
                return dep
        return None

    @LogError(logging)
    def get_packages(self) -> list:
        packages = []
        with open(path.join(self.home_path, "requirements.txt"), "r") as f:
            for line in f:
                library = line.strip().split("==")[0]
                if self.is_dependency_present(library):
                    packages.extend(self.get_dependency(library).packages)

        # Custom Packages
        if self.conf.custom_packages:
            packages.extend(self.conf.custom_packages)
        return list(set(packages))

    @LogError(logging)
    def generate_dockerfile(self):
        with open(path.join(self.home_path, "Dockerfile"), "w") as f:
            f.write(self.dockerfile_generator())
        shutil.copyfile(
            path.join(path.dirname(__file__), "templates/start.sh"),
            path.join(self.home_path, "start.sh"),
        )

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
                dependencies=self.get_packages(),
                entrypoint=self.conf.entrypoint,
            )
            return output

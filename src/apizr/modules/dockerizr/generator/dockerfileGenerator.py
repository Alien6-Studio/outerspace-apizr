import re
import shlex
from pathlib import Path

from jinja2 import Environment, StrictUndefined
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from apizr.output import write_new_text


class DockerfileGenerator:
    def __init__(self, conf):
        self.conf = conf
        self.home_path = Path(conf.project_path)

    def is_dependency_present(self, name):
        return self.get_dependency(name) is not None

    def get_dependency(self, name):
        return next(
            (
                dep
                for dep in self.conf.dependencies
                if canonicalize_name(dep.name) == canonicalize_name(name)
            ),
            None,
        )

    def get_packages(self):
        packages = set(self.conf.custom_packages)
        for line in (
            (self.home_path / "requirements.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        ):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            dependency = self.get_dependency(Requirement(line).name)
            if dependency:
                packages.update(dependency.packages)
        for package in packages:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]*", package):
                raise ValueError(f"Invalid system package name: {package}")
        return sorted(packages)

    def dockerfile_generator(self):
        tag = self.conf.docker_image_tag
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", tag):
            raise ValueError("Invalid Docker image tag")
        if self.conf.docker_image == "alpine" and not tag.startswith("alpine"):
            raise ValueError("Alpine images require an alpine image tag")
        if self.conf.docker_image == "debian" and tag.startswith("alpine"):
            raise ValueError("Debian images cannot use an Alpine tag")
        template = Environment(
            undefined=StrictUndefined, keep_trailing_newline=True
        ).from_string(
            Path(__file__)
            .with_name("templates")
            .joinpath(f"dockerfile-{self.conf.docker_image}.jinja")
            .read_text(encoding="utf-8")
        )
        return template.render(
            python_version=".".join(map(str, self.conf.python_version)),
            docker_image_tag=tag,
            port=self.conf.server.port,
            dependencies=self.get_packages(),
        )

    def generate_dockerfile(self):
        self.home_path.mkdir(parents=True, exist_ok=True)
        filenames = ["Dockerfile", "start.sh", ".dockerignore"]
        if self.conf.entrypoint:
            filenames.append("entrypoint.sh")
        for filename in filenames:
            target = self.home_path / filename
            if target.exists() or target.is_symlink():
                raise FileExistsError(f"Generated output already exists: {target}")
        dockerfile = self.dockerfile_generator()
        command = [
            "uvicorn",
            f"{self.conf.module_name}:app",
            "--host",
            self.conf.server.host,
            "--port",
            str(self.conf.server.port),
            "--workers",
            str(self.conf.server.workers),
            "--timeout-graceful-shutdown",
            str(self.conf.server.timeout),
        ]
        startup = "#!/bin/sh\nset -eu\n"
        if self.conf.entrypoint:
            startup += "sh ./entrypoint.sh\n"
            entrypoint = self.home_path / "entrypoint.sh"
            write_new_text(
                entrypoint,
                "#!/bin/sh\nset -eu\n" + self.conf.entrypoint + "\n",
                encoding="utf-8",
            )
            entrypoint.chmod(0o755)
        startup += "exec " + shlex.join(command) + "\n"
        write_new_text(self.home_path / "Dockerfile", dockerfile)
        write_new_text(self.home_path / "start.sh", startup)
        (self.home_path / "start.sh").chmod(0o755)
        write_new_text(
            self.home_path / ".dockerignore",
            ".git\n.venv\n__pycache__\n*.pyc\n.env\n.env.*\n*.ipynb\n",
            encoding="utf-8",
        )

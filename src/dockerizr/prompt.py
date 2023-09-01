import ast
import collections.abc
import json

# Patch pour PyInquirer et Python 3.10+
collections.Mapping = collections.abc.Mapping

from PyInquirer import prompt

from configuration import DockerizrConfiguration, GunicornConfiguration

HOSTNAME = "0.0.0.0"  # nosec B104


class ConfigPrompter:
    def __init__(self, lang: str = "en"):
        self.translations = self.load_translations(lang)

    def load_translations(self, lang: str) -> dict:
        try:
            with open(f"i18n/{lang}/messages.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Erreur lors du chargement des traductions : {e}")
            return {}

    def get_translation(self, key: str, **kwargs) -> str:
        return self.translations.get(key, "").format(**kwargs)

    def getConfiguration(self) -> DockerizrConfiguration:
        configuration = DockerizrConfiguration()
        configuration.python_version = tuple(
            map(int, self.prompt_python_version().split("."))
        )
        configuration.encoding = self.prompt_encoding()
        configuration.docker_image = self.prompt_docker_image()
        configuration.docker_image_tag = self.prompt_docker_image_tag()
        configuration.project_path = self.prompt_project_path()
        configuration.main_folder = self.prompt_main_folder()
        configuration.api_filename = self.prompt_api_filename()
        configuration.server = self.prompt_server_configuration()
        return configuration

    def prompt_python_version(self) -> str:
        default_version = "3.8"
        version = input(
            self.get_translation("version", default_version=default_version)
        )
        return version if version else default_version

    def prompt_encoding(self) -> str:
        default_encoding = "utf-8"
        encoding = input(
            self.get_translation("encoding", default_encoding=default_encoding)
        )
        return encoding if encoding else default_encoding

    def prompt_docker_image(self) -> str:
        questions = [
            {
                "type": "list",
                "name": "docker_image",
                "message": self.get_translation("docker_image"),
                "choices": ["alpine", "debian"],
                "default": "alpine",
            }
        ]
        return prompt(questions)["docker_image"]

    def prompt_docker_image_tag(self) -> str:
        image_tags = {
            "alpine": ["alpine", "alpine3.17", "alpine3.18", "latest"],
            "debian": ["slim", "buster", "bullseye"],
        }
        questions = [
            {
                "type": "list",
                "name": "docker_image_tag",
                "message": self.get_translation("docker_image_tag"),
                "choices": image_tags.get(self.prompt_docker_image(), []),
            }
        ]
        return prompt(questions)["docker_image_tag"]

    def prompt_project_path(self) -> str:
        return input(self.get_translation("project_path")) or "."

    def prompt_main_folder(self) -> str:
        return input(self.get_translation("main_folder"))

    def prompt_api_filename(self) -> str:
        return input(self.get_translation("api_filename")) or "app.py"

    def prompt_server_configuration(self) -> GunicornConfiguration:
        server_config = GunicornConfiguration()
        server_config.server_app = (
            input(self.get_translation("server_app")) or "gunicorn"
        )
        server_config.wsgi_file_name = (
            input(self.get_translation("wsgi_file_name")) or "wsgi.py"
        )
        server_config.wsgi_conf_file_name = (
            input(self.get_translation("wsgi_conf_file_name")) or "gunicorn.conf.py"
        )
        server_config.host = input(self.get_translation("host")) or HOSTNAME
        server_config.port = int(input(self.get_translation("port")) or 5001)
        server_config.workers = int(input(self.get_translation("workers")) or 2)
        server_config.timeout = int(input(self.get_translation("timeout")) or 60)
        return server_config

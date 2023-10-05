import collections.abc
import json
import os

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
            current_path = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(current_path, f"i18n/{lang}/messages.json")
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading translations: {e}")
            return {}

    def get_translation(self, key: str, **kwargs) -> str:
        return self.translations.get(key, "").format(**kwargs)

    def getConfiguration(
        self,
        version: tuple = None,
        encoding: str = "",
        api_filename: str = "",
        module_name: str = "",
        project_path: str = "",
    ) -> DockerizrConfiguration:
        """
        Prompt user for configuration
        """
        configuration = DockerizrConfiguration()

        # Version can be passed from Apizr
        if not version:
            configuration.python_version = tuple(
                map(int, self.prompt_python_version().split("."))
            )
        else:
            configuration.python_version = version

        # Encoding can be passed from Apizr
        if not encoding:
            configuration.encoding = self.prompt_encoding()
        else:
            configuration.encoding = encoding

        # API filename can be passed from Apizr
        if not api_filename:
            configuration.api_filename = self.prompt_api_filename(project_path)
        else:
            configuration.api_filename = api_filename

        # Module name can be passed from Apizr
        if not module_name:
            configuration.module_name = self.prompt_module_name()
        else:
            configuration.module_name = module_name

        # Project path can be passed from Apizr
        if not project_path:
            configuration.project_path = self.prompt_project_path()
        else:
            configuration.project_path = project_path

        # Docker configuration
        configuration.docker_image = self.prompt_docker_image()
        configuration.docker_image_tag = self.prompt_docker_image_tag(
            docker_image=configuration.docker_image
        )
        configuration.entrypoint = self.prompt_entrypoint()

        # Server configuration
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

    def prompt_docker_image_tag(self, docker_image: str) -> str:
        image_tags = {
            "alpine": ["alpine", "alpine3.17", "alpine3.18", "latest"],
            "debian": ["slim", "buster", "bullseye"],
        }
        questions = [
            {
                "type": "list",
                "name": "docker_image_tag",
                "message": self.get_translation("docker_image_tag"),
                "choices": image_tags.get(docker_image, []),
            }
        ]
        return prompt(questions)["docker_image_tag"]

    def prompt_project_path(self) -> str:
        return input(self.get_translation("project_path")) or "."

    def prompt_module_name(self) -> str:
        return input(self.get_translation("module_name"))

    def prompt_api_filename(self, project_path) -> str:
        files = [
            f
            for f in os.listdir(project_path)
            if os.path.isfile(os.path.join(project_path, f)) and f.endswith(".py")
        ]
        if not files:
            return "app.py"

        questions = [
            {
                "type": "list",
                "name": "file",
                "message": self.get_translation("api_filename"),
                "choices": files,
            }
        ]

        answers = prompt(questions)
        return answers["file"]

    def prompt_entrypoint(self) -> str:
        return input(self.get_translation("entrypoint"))

    def prompt_server_configuration(self) -> GunicornConfiguration:
        server_config = GunicornConfiguration()

        # ---------------------------------------------------------------------
        # Asking for the server is useless since we only support Gunicorn
        # We keep the code in case we want to support other servers in the future
        #
        # server_config.server_app = (input(self.get_translation("server_app")) or "gunicorn")
        # server_config.wsgi_file_name = (input(self.get_translation("wsgi_file_name")) or "wsgi.py")
        # server_config.wsgi_conf_file_name = (input(self.get_translation("wsgi_conf_file_name")) or "gunicorn.conf.py")

        server_config.host = input(self.get_translation("host")) or HOSTNAME
        server_config.port = int(input(self.get_translation("port")) or 5001)
        server_config.workers = int(input(self.get_translation("workers")) or 2)
        server_config.timeout = int(input(self.get_translation("timeout")) or 60)
        return server_config

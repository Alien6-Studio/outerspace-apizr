import ast
import collections.abc
import json
import os

# Patch pour PyInquirer et Python 3.10+
collections.Mapping = collections.abc.Mapping

from PyInquirer import prompt

from code_analyzr.prompt import ConfigPrompter as CodeAnalyzrConfigPrompter
from configuration import MainConfiguration
from dockerizr.prompt import ConfigPrompter as DockerizrConfigPrompter
from fast_apizr.prompt import ConfigPrompter as FastApizrConfigPrompter

HOSTNAME = "0.0.0.0"  # nosec B104


class ConfigPrompter:
    def __init__(self, code: str, script_name: str, lang: str = "en"):
        self.language = lang
        self.code = code
        self.script_name = script_name
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

    def getConfiguration(self, output_path) -> MainConfiguration:
        configuration = MainConfiguration()
        configuration.python_version = tuple(
            map(int, self.prompt_python_version().split("."))
        )

        configuration.encoding = self.prompt_encoding()

        # Init Prompts
        code_analyzr_prompt = CodeAnalyzrConfigPrompter(
            code_str=self.code, lang=self.language
        )
        fast_apizr_prompt = FastApizrConfigPrompter(lang=self.language)
        dockerizr_prompt = DockerizrConfigPrompter(lang=self.language)

        configuration.code_analyzr = code_analyzr_prompt.getConfiguration(
            version=configuration.python_version, encoding=configuration.encoding
        )
        api_filename = self.script_name.replace(".py", "_api.py")
        configuration.fast_apizr = fast_apizr_prompt.getConfiguration(
            version=configuration.python_version,
            encoding=configuration.encoding,
            api_filename=api_filename,
            module_name=self.script_name.replace(".py", ""),
        )
        configuration.dockerizr = dockerizr_prompt.getConfiguration(
            version=configuration.python_version,
            encoding=configuration.encoding,
            api_filename=configuration.fast_apizr.api_filename,
            module_name=configuration.fast_apizr.api_filename.replace(".py", ""),
            project_path=output_path,
        )

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

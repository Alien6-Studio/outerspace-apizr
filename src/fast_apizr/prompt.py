import ast
import collections.abc
import json

# Patch for PyInquirer and Python 3.10+
collections.Mapping = collections.abc.Mapping

from PyInquirer import prompt

from configuration import FastApizrConfiguration


class ConfigPrompter:
    def __init__(self, lang: str = "en"):
        self.translations = self.load_translations(lang)

    def load_translations(self, lang: str) -> dict:
        try:
            with open(f"i18n/{lang}/messages.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading translations: {e}")
            return {}

    def get_translation(self, key: str, **kwargs) -> str:
        return self.translations.get(key, "").format(**kwargs)

    def getConfiguration(self) -> FastApizrConfiguration:
        configuration = FastApizrConfiguration()
        configuration.python_version = tuple(
            map(int, self.prompt_python_version().split("."))
        )
        configuration.encoding = self.prompt_encoding()
        configuration.module_name = self.prompt_module_name()
        configuration.api_filename = self.prompt_api_filename()

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

    def prompt_module_name(self) -> str:
        default_module = "main"
        module_name = input(
            self.get_translation("module", default_module=default_module)
        )
        return prompt(module_name) if module_name else default_module

    def prompt_api_filename(self) -> str:
        default_filename = "app.py"
        api_filename = input(
            self.get_translation("filename", default_filename=default_filename)
        )
        return prompt(api_filename) if api_filename else default_filename

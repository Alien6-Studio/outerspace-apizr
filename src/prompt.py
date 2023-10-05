import collections.abc
import json
import os

# Patch pour PyInquirer et Python 3.10+
collections.Mapping = collections.abc.Mapping

from PyInquirer import prompt
from configuration import MainConfiguration


class ConfigPrompter:
    def __init__(self, lang: str = "en"):
        self.language = lang
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

    def getConfiguration(self) -> MainConfiguration:
        configuration = MainConfiguration()
        configuration.python_version = tuple(
            map(int, self.prompt_python_version().split("."))
        )
        configuration.encoding = self.prompt_encoding()
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

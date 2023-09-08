import ast
import collections.abc
import json
import os

# Patch for PyInquirer and Python 3.10+
collections.Mapping = collections.abc.Mapping

from PyInquirer import prompt

from configuration import CodeAnalyzrConfiguration


class ConfigPrompter:
    def __init__(self, code_str: str, lang: str = "en"):
        self.code_str = code_str
        self.function_names = self.extract_functions_from_code()
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

    def extract_functions_from_code(self) -> list:
        tree = ast.parse(self.code_str)
        return [
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]

    def getConfiguration(self, version=None, encoding=None) -> CodeAnalyzrConfiguration:
        configuration = CodeAnalyzrConfiguration()
        if not version:
            configuration.python_version = tuple(
                map(int, self.prompt_python_version().split("."))
            )
        if not encoding:
            configuration.encoding = self.prompt_encoding()

        method = self.get_configuration_method()
        if method == self.translations["method"]["specify_analyze"]:
            configuration.functions_to_analyze = self.prompt_functions_to_analyze()
        elif method == self.translations["method"]["specify_ignore"]:
            configuration.ignore = self.prompt_functions_to_ignore()
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

    def get_configuration_method(self) -> str:
        questions = [
            {
                "type": "list",
                "name": "method",
                "message": self.translations["method"]["title"],
                "choices": [
                    self.translations["method"]["specify_analyze"],
                    self.translations["method"]["specify_ignore"],
                    self.translations["method"]["take_all"],
                ],
            }
        ]
        return prompt(questions)["method"]

    def prompt_functions_to_analyze(self) -> str:
        choices = [{"name": func_name} for func_name in self.function_names]
        questions = [
            {
                "type": "checkbox",
                "name": "functions",
                "message": self.translations["analyze"],
                "choices": choices,
            }
        ]
        selected_functions = prompt(questions)["functions"]
        return ",".join(selected_functions)

    def prompt_functions_to_ignore(self) -> str:
        choices = [{"name": func_name} for func_name in self.function_names]
        questions = [
            {
                "type": "checkbox",
                "name": "functions",
                "message": self.translations["ignore"],
                "choices": choices,
            }
        ]
        ignored_functions = prompt(questions)["functions"]
        return ",".join(ignored_functions)

import ast
import json
import logging
import sys

from configuration import CodeAnalyzrConfiguration

from .ast_node import FunctionNode, ImportFromNode, ImportNode, LogError
from .exceptions import UnsupportedKeywordError


# AstAnalyzr class analyzes the structure of a Python code using Abstract Syntax Tree (AST).
class AstAnalyzr(ast.NodeVisitor):
    def __init__(self, configuration: CodeAnalyzrConfiguration, code_str: str):
        """Initialize the AstAnalyzr with code string and Python version.

        Args:
            configuration (CodeAnalyzrConfiguration): The configuration object.
            code_str (str): The Python code string to be analyzed.
        """
        self.code_str: str = code_str
        self.version: tuple = configuration.python_version
        self.keywords = configuration.keywords
        # Convert comma-separated string to list
        self.functions_to_analyze = (
            configuration.functions_to_analyze.split(",")
            if configuration.functions_to_analyze
            else []
        )
        self.ignore = configuration.ignore.split(",") if configuration.ignore else []
        self.imports = []
        self.imports_from = []
        self.functions = []

    @LogError(logging)
    def check_for_keywords(self, code_str):
        version = sys.version_info[:2]
        if not isinstance(self.keywords, list):
            logging.error("self.keywords is not a list.")
            return

        for keywords in self.keywords:
            if not isinstance(keywords, dict):
                logging.error(f"Unexpected type in self.keywords: {type(keywords)}")
                continue

            version_key = keywords.get("version")
            values_key = keywords.get("values")

            if not version_key or not values_key:
                logging.error("Missing 'version' or 'values' key in keywords entry.")
                continue

            ver = tuple(map(int, version_key.split(".")))
            for keyword in values_key:
                if keyword in code_str and version < ver:
                    raise UnsupportedKeywordError(keyword, ver, version)

    @LogError(logging)
    def get_analyse(self):
        """Analyze the provided code string and return its structure in JSON format.

        Returns:
            str: A JSON string representing the structure of the analyzed code.
        """
        try:
            self.check_for_keywords(self.code_str)
            self.generic_visit(
                ast.parse(
                    self.code_str, type_comments=True, feature_version=self.version
                )
            )
            return self.toJSON()
        except UnsupportedKeywordError as e:
            return json.dumps({"error": str(e)})

    @LogError(logging)
    def generic_visit(self, node):
        """Override the generic_visit method to handle specific node types.

        Args:
            node (ast.AST): The current AST node being visited.
        """

        # Handle 'import' statements
        if isinstance(node, ast.Import):
            self.imports.extend(ImportNode(alias) for alias in node.names)
        # Handle 'import from' statements
        elif isinstance(node, ast.ImportFrom):
            self.imports_from.append(ImportFromNode(node))
        # Handle function definitions
        elif isinstance(node, ast.FunctionDef):
            if self.functions_to_analyze and node.name not in self.functions_to_analyze:
                pass  # Skip this function if its name is not in functions_to_analyze
            elif node.name in self.ignore:
                pass  # Skip this function if its name is in ignore
            else:
                self.functions.append(FunctionNode(node))
        # @TODO: Handle class definitions and other node types as needed.
        elif isinstance(node, ast.ClassDef):
            pass
        else:
            ast.NodeVisitor.generic_visit(self, node)

    def toJSON(self):
        """Convert the current state of the analyzer to JSON format.

        Returns:
            str: A JSON string representation of the current state.
        """
        return json.dumps(
            self.__getstate__(), default=lambda o: o.__getstate__(), indent=2
        )

    def __getstate__(self):
        """Helper method to get the state of the object for JSON serialization.

        Returns:
            dict: A dictionary representing the object's state.
        """
        state = dict(self.__dict__)
        del state["code_str"]
        return state

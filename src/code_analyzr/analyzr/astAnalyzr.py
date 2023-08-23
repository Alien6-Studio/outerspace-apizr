import sys
import ast
import json
import logging

from .ast_node import FunctionNode
from .ast_node import ImportNode
from .ast_node import ImportFromNode
from .ast_node import LogError

from .exceptions import UnsupportedKeywordError


# AstAnalyzr class analyzes the structure of a Python code using Abstract Syntax Tree (AST).
class AstAnalyzr(ast.NodeVisitor):
    KEYWORDS = {(3, 10): ["match", "case"]}

    def __init__(
        self, code_str, functions_to_analyze=None, ignore=None, version=(3, 8)
    ):
        """Initialize the AstAnalyzr with code string and Python version.

        Args:
            code_str (str): The Python code string to be analyzed.
            version (tuple): The Python version tuple (e.g., (3, 8) for Python 3.8).
        """
        self.code_str = code_str
        self.version = version

        # Convert comma-separated string to list
        self.functions_to_analyze = (
            functions_to_analyze.split(",") if functions_to_analyze else []
        )
        self.ignore = ignore.split(",") if ignore else []
        self.imports = []
        self.imports_from = []
        self.functions = []

    @LogError(logging)
    def check_for_keywords(self, code_str):
        version = sys.version_info[:2]
        for ver, keywords in self.KEYWORDS.items():
            for keyword in keywords:
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

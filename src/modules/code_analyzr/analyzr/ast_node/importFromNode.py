import ast

from .astNode import AstNode
from .importNode import ImportNode


class ImportFromNode(AstNode):
    """Represents 'from ... import ...' statements in the AST.

    This class processes and represents 'from ... import ...' statements found in the Python code.
    It extracts information such as the module name, the imported elements, and the import level.
    """

    def __init__(self, node):
        """Initialize the ImportFromNode with the given AST node.

        Args:
            node (ast.ImportFrom): The AST node representing the 'from ... import ...' statement.
        """
        super().__init__(node)
        # Initialize the module with the node's module or an empty string if the module is None
        self.module = node.module if node.module else ""
        self.imports = [ImportNode(alias) for alias in node.names]
        self.level = node.level

from .astNode import AstNode


class ImportNode(AstNode):
    """Represents individual imported elements in 'import' or 'from ... import ...' statements in the AST.

    This class processes and represents individual imported elements found in the Python code.
    It extracts information such as the name of the imported element and its alias (if any).
    """

    def __init__(self, node):
        """Initialize the ImportNode with the given AST node.

        Args:
            node (ast.alias): The AST node representing the imported element in an 'import' statement.
        """
        super().__init__(node)
        self.name = node.name
        # The alias for the imported name (e.g., 'import numpy as np' where 'np' is the alias for 'numpy')
        self.asname = node.asname

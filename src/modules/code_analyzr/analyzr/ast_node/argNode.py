import logging

from .annotationNode import AnnotationNode
from .astNode import AstNode
from .errorLogger import LogError


class ArgNode(AstNode):
    """Represents function arguments in the AST.

    This class processes and represents function arguments found in the Python code.
    It extracts the argument name and its type annotation.
    """

    def __init__(self, node, default_value=None):
        """Initialize the ArgNode with the given AST node and default value (if any).

        Args:
            node (ast.arg): The AST node representing the function argument.
            default_value: The default value for the argument (if any).
        """
        super().__init__(node)
        self.name = node.arg
        self.annotation = self.get_annotation()

    @LogError(logging)
    def get_annotation(self):
        """Retrieve the type annotation for the function argument.

        Returns:
            AnnotationNode: An AnnotationNode representing the type annotation.
        """
        return AnnotationNode(self.node.annotation)

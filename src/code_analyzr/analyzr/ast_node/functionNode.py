import logging
import warnings

from .annotationNode import AnnotationNode
from .argNode import ArgNode
from .astNode import AstNode
from .errorLogger import LogError


class FunctionNode(AstNode):
    """Represents function definitions in the AST.

    This class processes and represents function definitions found in the Python code.
    It extracts information such as the function name, its arguments, and return type annotation.
    """

    def __init__(self, node):
        """Initialize the FunctionNode with the given AST node.

        Args:
            node (ast.FunctionDef): The AST node representing the function definition.
        """
        super().__init__(node)
        self.name = node.name
        self.args = self.get_args()
        self.returns = self.get_annotation()
        self.selected = True

    @LogError(logging)
    def get_args(self):
        """Retrieve the arguments of the function.

        Returns:
            list: A list of ArgNode objects representing each argument of the function.
        """
        # @TODO: Handle positional only arguments and raise appropriate exceptions.
        if self.node.args.posonlyargs:
            pass
        # @TODO: Handle variable arguments and raise appropriate exceptions.
        if hasattr(self.node.args, "varargs"):
            pass
        # @TODO: Handle keyword only arguments and raise appropriate exceptions.
        if self.node.args.kwonlyargs:
            pass
        # @TODO: Handle keyword arguments and raise appropriate exceptions.
        if hasattr(self.node.args, "kwargs"):
            pass
        return [ArgNode(arg_node) for arg_node in self.node.args.args]

    @LogError(logging)
    def get_annotation(self):
        """Retrieve the return type annotation of the function.

        Returns:
            AnnotationNode: An AnnotationNode representing the return type annotation.
        """
        return AnnotationNode(self.node.returns)

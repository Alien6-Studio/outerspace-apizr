import ast
import sys

from typing import List, Optional, Union
from .astNode import AstNode
from .astNodeException import AnnotationException


class AnnotationNode(AstNode):
    """Represents type annotations in the AST.

    This class processes and represents type annotations found in the Python code.
    It handles basic types, complex types like List and Tuple, and other type constructs.
    """

    def __init__(self, node):
        """Initialize the AnnotationNode with the given AST node.

        Args:
            node (ast.AST): The AST node representing the type annotation.
        """
        super().__init__(node)
        self.type = "any"
        self.of = []
        self.type = self._get_type(node) if node is not None else "any"

    def _get_type(self, node):
        """Determine the type based on the given AST node.

        Args:
            node (ast.AST): The AST node to determine the type from.

        Returns:
            str: The determined type as a string.
        """
        if isinstance(node, ast.Attribute):
            return self._get_type(node.value) + "." + node.attr
        elif isinstance(node, ast.Subscript):
            return self.parse_subscript(node)
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.List):
            return self.parse_list(node)
        elif isinstance(node, ast.Tuple):
            self.of = [AnnotationNode(elt) for elt in node.elts] if node.elts else []
            return "Tuple"
        elif isinstance(node, ast.Constant):
            return "None" if node.value is None else type(node.value).__name__
        elif isinstance(node, ast.BinOp):
            # Handle binary operations in type annotations
            left_type = self._get_type(node.left)
            right_type = self._get_type(node.right)

            # Determine the type of binary operation
            if isinstance(node.op, ast.BitOr):  # Represents the "|" operator
                binary_op = "Union"
            elif isinstance(
                node.op, ast.BitAnd
            ):  # Represents the "&" operator (used for Intersection)
                binary_op = "Intersection"
            # Add checks for other binary operations here if needed
            else:
                raise AnnotationException(
                    f"Unsupported binary operation: {type(node.op)}"
                )

            self.of = [left_type, right_type]
            return binary_op
        else:
            raise AnnotationException(f"Unhandled node type: {type(node)}")

    def parse_subscript(self, node):
        """Parse subscript type annotations like List[int] or Dict[str, int].

        Args:
            node (ast.Subscript): The AST node representing the subscript type annotation.

        Returns:
            str: The base type of the annotation (e.g., 'List' for List[int]).
        """
        ty = self._get_type(node.value)
        if ty in ["Tuple", "typing.Tuple"]:
            self.of = self.parse_tuple(node.slice)
            return ty
        else:
            if sys.version_info >= (3, 9):
                self.of.append(AnnotationNode(node.slice))
            else:
                self.of.append(AnnotationNode(node.slice.value))
            return ty

    def parse_list(self, node):
        """Parse list type annotations like List[int].

        Args:
            node (ast.List): The AST node representing the list type annotation.

        Returns:
            str: The string 'List'.
        """
        self.of.extend([AnnotationNode(elt) for elt in node.elts] if node.elts else [])

        # --- Old code ---
        #
        # if len(node.elts) > 1:
        #    self.of.extend([AnnotationNode(elt) for elt in node.elts] if node.elts else [])
        # elif node.elts:
        #    self.of.append(AnnotationNode(node.elts[0]))
        #
        # --- End of old code ---
        return "List"

    def parse_tuple(self, node):
        """Parse tuple type annotations like Tuple[int, str].

        Args:
            node (ast.Subscript or ast.Tuple): The AST node representing the tuple type annotation.

        Returns:
            list: A list of AnnotationNodes representing each type in the tuple.
        """
        if sys.version_info >= (3, 9):
            value = node
        else:
            value = node.value
        if isinstance(value, ast.Tuple):
            return [AnnotationNode(elt) for elt in value.elts] if value.elts else []
        raise AnnotationException()

class AstNode(object):
    """Base class for representing AST nodes in the analyzer.

    This class serves as a base for other classes that represent specific types of AST nodes.
    It provides common functionality for managing and representing AST nodes.
    """

    def __init__(self, node):
        """Initialize the AstNode with the given AST node.

        Args:
            node (ast.AST): The AST node to be represented by this object.
        """
        super().__init__()
        self.node = node

    def __getstate__(self):
        """Retrieve the state of the object for serialization.

        This method is used to get the object's state, excluding the 'node' attribute.

        Returns:
            dict: A dictionary representing the object's state.
        """
        state = dict(self.__dict__)
        del state["node"]
        return state

    def __str__(self):
        """Provide a string representation of the AstNode object.

        Returns:
            str: A string representation of the object, showing its type and state.
        """
        return f"""
            node type : {type(self.node).__name__}
            obj: {self.__getstate__()}
        """

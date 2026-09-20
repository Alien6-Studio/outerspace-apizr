class AnnotationException(TypeError):
    """Exception raised for errors during type retrieval in AST nodes.

    This exception is a subtype of TypeError and is used to indicate issues related
    to type annotations in the Abstract Syntax Tree.
    """

    def __init__(self, message: str = "error while retrieving type"):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return self.message

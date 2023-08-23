class AnnotationException(TypeError):
    """Exception raised for errors during type retrieval in AST nodes.

    This exception is a subtype of TypeError and is used to indicate issues related
    to type annotations in the Abstract Syntax Tree.
    """

    def __init__(self):
        super().__init__()

    def __str__(self):
        return "error while retrieving type"

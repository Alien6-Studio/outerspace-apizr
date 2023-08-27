from pydantic import BaseModel

from .annotation import Annotation


class Argument(BaseModel):
    """Represents a function argument with its name and type annotation.

    This model captures details about an argument of a function, including its
    name and the associated type annotation, which is represented using the
    Annotation class.
    """

    name: str  # The name of the argument.
    annotation: Annotation  # The type annotation for the argument.

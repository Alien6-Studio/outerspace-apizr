from typing import Optional

from pydantic import BaseModel


class Import(BaseModel):
    """Represents a direct import statement with its name and optional alias.

    This model captures details about a direct import statement, including the
    name of the imported module or library and an optional alias (if specified
    using the 'as' keyword).
    """

    name: str  # The name of the imported module or library.
    asname: Optional[str] = None  # Optional alias for the imported module or library.
    module: Optional[str] = None  # Optional module from which the name is imported.

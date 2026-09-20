from typing import List

from pydantic import BaseModel

from .imports import Import


class ImportFrom(BaseModel):
    """Represents a 'from ... import ...' statement with details of the origin module and imported items.

    This model captures details about a 'from ... import ...' statement, including
    the name of the origin module, the list of imported items, and the relative
    import level (if specified).
    """

    module: str  # The name of the origin module.
    imports: List[Import]  # List of items imported from the origin module.
    level: int = 0  # Relative import level (default is 0).

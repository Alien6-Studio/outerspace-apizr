"""Load the explicit embedded package without modifying sys.path or importing source."""

import importlib.util
import sys
from pathlib import Path


def activate(root: Path) -> None:
    package = root / "apizr_governed"
    spec = importlib.util.spec_from_file_location(
        "apizr_governed",
        package / "__init__.py",
        submodule_search_locations=[str(package)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Governed runtime unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules["apizr_governed"] = module
    spec.loader.exec_module(module)

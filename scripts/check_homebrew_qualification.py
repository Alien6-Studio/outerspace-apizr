"""Compatibility CLI for scripts.qualification.packaging.check_homebrew_qualification."""

import runpy
import sys
from importlib import import_module
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "scripts/qualification/packaging/check_homebrew_qualification.py"
        ),
        run_name="__main__",
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    _implementation = import_module(
        "scripts.qualification.packaging.check_homebrew_qualification"
    )
    sys.modules[__name__] = _implementation
    globals().update(vars(_implementation))

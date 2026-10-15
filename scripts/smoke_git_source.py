"""Compatibility CLI for scripts.qualification.repository.smoke_git_source."""

import runpy
import sys
from importlib import import_module
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "scripts/qualification/repository/smoke_git_source.py"
        ),
        run_name="__main__",
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    _implementation = import_module("scripts.qualification.repository.smoke_git_source")
    sys.modules[__name__] = _implementation
    globals().update(vars(_implementation))

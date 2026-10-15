#!/usr/bin/python3
"""Compatibility CLI for scripts.qualification.fixtures.oras_transfer_observer."""

import runpy
import sys
from importlib import import_module
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "scripts/qualification/fixtures/oras_transfer_observer.py"
        ),
        run_name="__main__",
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    _implementation = import_module(
        "scripts.qualification.fixtures.oras_transfer_observer"
    )
    sys.modules[__name__] = _implementation
    globals().update(vars(_implementation))

"""Observe real pip PEP 517 dynamic requirements without changing their result."""

import importlib
import json
import os
import runpy
import sys
from pathlib import Path

# pip belongs to the disposable Homebrew frontend, not the project environment.
caller = importlib.import_module("pip._vendor.pyproject_hooks").BuildBackendHookCaller
original = caller.get_requires_for_build_wheel


def requirements(self, config_settings=None):
    result = original(self, config_settings)
    path = Path(os.environ["APIZR_BUILD_PROOF_ROOT"]) / "dynamic-requirements.jsonl"
    with path.open("a") as stream:
        stream.write(json.dumps(result) + "\n")
    return result


caller.get_requires_for_build_wheel = requirements
sys.argv = ["pip", *sys.argv[1:]]
runpy.run_module("pip", run_name="__main__")

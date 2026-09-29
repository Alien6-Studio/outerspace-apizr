"""Share installed-qualification parity assertions without changing import search paths."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "bundle_provenance_assertions",
    Path(__file__).parents[1] / "scripts/bundle_provenance_assertions.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert_equivalent_bundles = module.assert_equivalent_bundles

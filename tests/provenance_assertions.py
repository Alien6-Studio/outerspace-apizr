"""Share installed-qualification parity assertions without changing import search paths."""

import importlib.util

from qualification_scripts import implementation as qualification_script

spec = importlib.util.spec_from_file_location(
    "bundle_provenance_assertions",
    str(qualification_script("bundle_provenance_assertions")),
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert_equivalent_bundles = module.assert_equivalent_bundles

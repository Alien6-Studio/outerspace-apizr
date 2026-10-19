"""Default built-in ownership, bounded contract use and pre-extraction byte parity."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.provider_source import SourceView
from apizr.experiments.reporting import inspection_bytes, text_report
from apizr.scientific_providers.builtin import BuiltinProvider
from apizr.scientific_providers.contracts import (
    ProducerIdentity,
    ProviderDescriptor,
    ProviderLimits,
    ProviderRequest,
    StaticProvider,
    admit_result,
)

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "tests/fixtures/experiments/builtin-baseline"
MANIFEST = json.loads((BASELINE / "manifest.json").read_text())
SOURCE = """import pandas as pd
import numpy as np
import joblib
from sklearn.metrics import accuracy_score
np.random.seed(42)
data = pd.read_csv("data/train.csv")
score = accuracy_score(y, predicted)
joblib.dump(model, "model.joblib")
"""


def test_admission_compatibility_exports_forward_to_the_contract_owner():
    from apizr.scientific_providers import admission
    from apizr.scientific_providers.contracts import admission as canonical

    for name in admission.__all__:
        assert getattr(admission, name) is getattr(canonical, name)


@pytest.mark.parametrize("case", MANIFEST["cases"], ids=lambda case: case["artifact"])
def test_pre_extraction_inspection_bytes_are_unchanged(tmp_path, case):
    expected = (BASELINE / case["artifact"]).read_bytes()
    assert len(expected) == case["size"]
    assert hashlib.sha256(expected).hexdigest() == case["sha256"]
    snapshot = MANIFEST.get("frozen_projects", {}).get(case["fixture"])
    if snapshot:
        for entry in snapshot["files"]:
            data = (ROOT / case["fixture"] / entry["path"]).read_bytes()
            assert len(data) == entry["bytes"]
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    project = tmp_path / "relocated"
    shutil.copytree(ROOT / case["fixture"], project)
    result = inspect_experiment(project / case["target"])
    actual = (
        inspection_bytes(result)
        if case["artifact"].endswith(".json")
        else text_report(result).encode()
    )
    assert actual == expected


@pytest.mark.parametrize(
    "capabilities",
    [
        ("metric_signals", "output_candidates", "randomness_controls", "input_reads"),
        ("metric_signals",),
        ("output_candidates",),
        ("randomness_controls",),
        ("input_reads",),
    ],
)
def test_reference_provider_honors_selected_capabilities(capabilities):
    provider: StaticProvider = BuiltinProvider()
    descriptor = ProviderDescriptor(
        identity=provider.descriptor.identity, capabilities=capabilities
    )
    request = ProviderRequest(
        provider=descriptor, source=SourceView(reference="train.py", text=SOURCE)
    )
    result = provider.recognize(request)
    assert admit_result(result, request=request) == result
    assert result.identity.name == "apizr.builtin"
    assert result.source_digest == hashlib.sha256(SOURCE.encode()).hexdigest()
    for capability, collection in (
        ("metric_signals", "signals"),
        ("output_candidates", "signals"),
        ("randomness_controls", "controls"),
        ("input_reads", "artifacts"),
    ):
        assert bool(getattr(getattr(result, capability), collection)) == (
            capability in capabilities
        )


def test_reference_provider_rejects_other_identity_and_aggregate_limits():
    provider = BuiltinProvider()
    source = SourceView(reference="train.py", text=SOURCE)
    other = ProviderDescriptor(
        identity=ProducerIdentity(name="other.provider", version="1"),
        capabilities=("metric_signals",),
    )
    with pytest.raises(ValueError, match="^provider_identity_mismatch$"):
        provider.recognize(ProviderRequest(provider=other, source=source))
    lowered = ProviderDescriptor(
        identity=provider.descriptor.identity,
        capabilities=provider.descriptor.capabilities,
        limits=ProviderLimits(max_evidence=1),
    )
    with pytest.raises(ValueError, match="^provider_result_invalid$"):
        provider.recognize(ProviderRequest(provider=lowered, source=source))


def test_default_discovery_preserves_individual_limits_and_encoded_bytes():
    from apizr.experiments import discover_inputs, discover_metrics, discover_outputs

    source = (
        "import pandas as pd\nimport joblib\nfrom sklearn.metrics import accuracy_score\n"
        + "\n".join(
            f'pd.read_csv("data/{i}.csv"); joblib.dump(model, "model.joblib"); accuracy_score(y, p)'
            for i in range(256)
        )
    )
    assert len(discover_inputs(source, source_reference="train.py").artifacts) == 256
    assert len(discover_metrics(source, source_reference="train.py").signals) == 256
    assert len(discover_outputs(source, source_reference="train.py").signals) == 256
    encoded = b'# coding: latin-1\nimport pandas as pd\npd.read_csv("caf\xe9.csv")\n'
    assert (
        discover_inputs(encoded, source_reference="train.py").artifacts[0].reference
        == "caf\u00e9.csv"
    )


def test_builtin_does_not_import_scientific_libraries_or_execute_source():
    code = (
        """
import importlib.abc
import sys

class RejectScientificImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.split(".")[0] in {"numpy", "pandas", "sklearn", "joblib", "torch", "tensorflow"}:
            raise AssertionError("Scientific dependency imported: " + fullname)

sys.meta_path.insert(0, RejectScientificImports())
from apizr.experiments import discover_inputs, discover_metrics, discover_outputs, discover_randomness
source = "raise AssertionError('Workload executed')\\n" + %r
assert discover_inputs(source, source_reference="train.py").artifacts
assert discover_metrics(source, source_reference="train.py").signals
assert discover_outputs(source, source_reference="train.py").signals
assert discover_randomness(source, source_reference="train.py").controls
"""
        % SOURCE
    )
    subprocess.run([sys.executable, "-I", "-c", code], check=True, capture_output=True)

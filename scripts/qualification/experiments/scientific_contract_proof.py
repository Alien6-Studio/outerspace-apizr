"""Exercise installed scientific contracts and SDK reporting outside the checkout."""

import argparse
import base64
import csv
import hashlib
import io
import json
import sys
import tomllib
import zipfile
from pathlib import Path

import apizr
from apizr import tracking
from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.metrics import discover_metrics
from apizr.experiments.provider_source import SourceView
from apizr.extension_runtime.protocol import Request, validate_response
from apizr.scientific_providers import (
    RECOGNIZE_OPERATION,
    ProducerIdentity,
    ProviderDescriptor,
    ProviderRequest,
    ProviderResult,
    SDKAdapterDescriptor,
    admit_extension_response,
    admit_result,
    extension_arguments,
)
from apizr.scientific_providers.builtin import BuiltinProvider
from apizr.tracking.adapters import AdapterReporter
from apizr.tracking.session import TrackingError


def alternative_provider_proof(root: Path) -> dict[str, object]:
    """Build and invoke an actual dependency-free, separately installed wheel."""
    from importlib.metadata import distributions

    from apizr.experiments.comparison import ChangeState, compare_stored_runs
    from apizr.experiments.history import show_run, show_text
    from apizr.experiments.runner import run_experiment
    from apizr.plugins.local import (
        disable_extension,
        enable_extension,
        install_extension,
        uninstall_extension,
    )
    from apizr.scientific_providers.contracts.selection import (
        ProviderChoice,
        ProviderSelection,
    )
    from apizr.scientific_providers.selection import list_providers

    fixture = Path(__file__).parent / "alternative-provider"
    project = tomllib.loads((fixture / "pyproject.toml").read_text())["project"]
    before = sorted((d.metadata["Name"], d.version) for d in distributions())
    name, version = project["name"], project["version"]
    info = f"{name.replace('-', '_')}-{version}.dist-info"
    payload = {
        p.relative_to(fixture / "src").as_posix(): p.read_bytes()
        for p in (fixture / "src").rglob("*.py")
    }
    payload.update(
        {
            "apizr-extension.json": (fixture / "apizr-extension.json").read_bytes(),
            f"{info}/licenses/LICENSE": (fixture / "LICENSE").read_bytes(),
            f"{info}/METADATA": f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\nRequires-Python: {project['requires-python']}\nLicense-Expression: GPL-3.0-or-later\nLicense-File: LICENSE\n\n".encode(),
            f"{info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: apizr-qualification\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        }
    )
    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for path, raw in sorted(payload.items()):
        writer.writerow(
            (
                path,
                "sha256="
                + base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
                .rstrip(b"=")
                .decode(),
                len(raw),
            )
        )
    writer.writerow((f"{info}/RECORD", "", ""))
    payload[f"{info}/RECORD"] = record.getvalue().encode()
    work = root / "external-provider-proof"
    work.mkdir()
    wheel = work / f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path, raw in sorted(payload.items()):
            archive.writestr(path, raw)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    directory = work / "plugins"
    installed = install_extension(
        wheel, digest, directory=directory, python=Path(sys.executable)
    )
    enable_extension(name, version, directory=directory)
    choice = ProviderChoice(
        identity=ProducerIdentity(name="example.literal-accuracy", version="1"),
        capabilities=("metric_signals",),
        extension=name,
    )
    selected = ProviderSelection(providers=(choice, *ProviderSelection().providers))
    inventory = list_providers(selected, directory=directory)
    assert inventory.active[0] == choice.identity
    source = work / "literal.py"
    source.write_text(
        "from sklearn.metrics import accuracy_score\nscore = accuracy_score([1], [1])\n"
    )
    observed = inspect_experiment(
        source, providers=selected, provider_directory=directory
    )
    assert len(observed.metrics.signals) == 1
    assert (
        observed.providers is not None
        and observed.providers.owners[1].provider == choice.identity
    )
    for refused in (
        "score = accuracy_score([1], [1])\nfrom sklearn.metrics import accuracy_score\n",
        "from sklearn.metrics import accuracy_score\naccuracy_score = other\nscore = accuracy_score([1], [1])\n",
        "from sklearn.metrics import accuracy_score\nscore = accuracy_score(actual, predicted)\n",
        "from sklearn.metrics import accuracy_score\nvalue = mutate_namespace()\nscore = accuracy_score([1], [1])\n",
    ):
        source.write_text(refused)
        negative = inspect_experiment(
            source, providers=selected, provider_directory=directory
        )
        assert not negative.metrics.signals
    source.write_text("score = 0.75\n")
    first = run_experiment(source, providers=selected, provider_directory=directory)
    disabled = ProviderSelection(
        providers=(
            choice.model_copy(update={"enabled": False}),
            *ProviderSelection().providers,
        )
    )
    second = run_experiment(source, providers=disabled, provider_directory=directory)
    disable_extension(name, directory=directory)
    removed = uninstall_extension(name, version, directory=directory)
    assert removed.exit_code == 0 and removed.environment_removed
    unavailable = list_providers(selected, directory=directory)
    assert unavailable.providers[0].diagnostic == "provider_unavailable"
    from apizr.experiments.store import DEFAULT_STORE

    history = work / DEFAULT_STORE
    retained = show_run(history, first.run_digest)
    assert "example.literal-accuracy 1" in show_text(retained)
    diff = compare_stored_runs(history, first.run_digest, second.run_digest)
    assert diff.providers is not None and diff.providers.state == ChangeState.CHANGED
    assert sorted((d.metadata["Name"], d.version) for d in distributions()) == before
    return {
        "wheel_sha256": digest,
        "isolated_python": installed.python,
        "explicit_protocol": "apizr.extension/v1",
        "positive_recognition": "passed",
        "negative_recognition": "passed",
        "disabled": "unknown",
        "removed_provider_history": "passed",
        "core_environment_unchanged": True,
    }


def prove(root: Path) -> dict[str, object]:
    source = SourceView(
        reference="example.py",
        text='from sklearn.metrics import accuracy_score\nlabel = "a\u2028b"\nscore = accuracy_score([1], [1])\n',
    )
    identity = ProducerIdentity(name="qualification.static", version="1.0")
    request = ProviderRequest(
        provider=ProviderDescriptor(
            identity=identity, capabilities=("metric_signals",)
        ),
        source=source,
    )
    result = ProviderResult(
        identity=identity,
        source=source.reference,
        source_digest=source.digest,
        metric_signals=discover_metrics(source.text, source_reference=source.reference),
    )
    wire = Request.model_validate(
        {
            "protocol": "apizr.extension/v1",
            "request_id": "a" * 32,
            "operation": RECOGNIZE_OPERATION,
            "arguments": extension_arguments(request),
        }
    )
    response = validate_response(
        json.dumps(
            {
                "protocol": wire.protocol,
                "request_id": wire.request_id,
                "operation": wire.operation,
                "status": "ok",
                "result": result.model_dump(mode="json"),
            }
        ).encode(),
        wire,
    )
    assert admit_extension_response(response, request=request) == result
    assert source.digest == hashlib.sha256(source.text.encode()).hexdigest()
    rejected = result.model_dump(mode="json") | {"source_digest": "b" * 64}
    try:
        admit_result(rejected, request=request)
    except ValueError as error:
        assert str(error) == "provider_result_invalid"
    else:
        raise AssertionError("Mismatched source evidence admitted")
    reporter = AdapterReporter(
        SDKAdapterDescriptor(
            identity=ProducerIdentity(name="qualification.adapter", version="1.0"),
            capabilities=("metric",),
        )
    )
    with tracking.session(root=root) as capture:
        reporter.log_metric("selected_observation", 0.75)
    assert capture.record is not None and capture.record.run.metrics[0].value == 0.75
    with tracking.session(root=root) as failed:
        try:
            reporter.log_metric("invalid_observation", float("nan"))
        except TrackingError as error:
            assert str(error) == "tracking_metric_invalid"
        else:
            raise AssertionError("Non-finite adapter metric admitted")
    assert failed.record is not None and failed.record.run.status == "failed"
    builtin = BuiltinProvider()
    builtin_source = SourceView(
        reference="builtin.py",
        text=source.text
        + "import pandas as pd\nimport numpy as np\nimport joblib\n"
        + 'np.random.seed(42)\ndata = pd.read_csv("data/train.csv")\n'
        + 'joblib.dump(model, "model.joblib")\n',
    )
    builtin_request = ProviderRequest(
        provider=builtin.descriptor, source=builtin_source
    )
    recognized = builtin.recognize(builtin_request)
    (root / builtin_source.reference).write_text(builtin_source.text, encoding="utf-8")
    inspected = inspect_experiment(root / builtin_source.reference)
    assert inspected.metrics == recognized.metric_signals
    assert inspected.outputs == recognized.output_candidates
    assert inspected.randomness == recognized.randomness_controls
    assert len(inspected.data.artifacts) == len(recognized.input_reads.artifacts) == 1
    assert inspected.data.artifacts[0].reference == "data/train.csv"
    assert recognized.input_reads.artifacts[0].digest is None
    assert len(recognized.metric_signals.signals) == 1
    assert len(recognized.output_candidates.signals) == 1
    assert len(recognized.randomness_controls.controls) == 1
    return {
        "status": "passed",
        "installed_package": apizr.__file__,
        "source_digest": source.digest,
        "static_result_schema": result.schema_version,
        "sdk_run_schema": capture.record.run.schema_version,
        "source_mismatch": "refused",
        "non_finite_adapter_value": "refused",
        "builtin_identity": builtin.descriptor.identity.model_dump(mode="json"),
        "builtin_default_inspection": "passed",
        "builtin_capabilities": list(builtin.descriptor.capabilities),
        "alternative_provider": alternative_provider_proof(root),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = prove(Path.cwd())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()

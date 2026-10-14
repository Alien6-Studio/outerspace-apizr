"""Exercise installed scientific contracts and SDK reporting outside the checkout."""

import argparse
import hashlib
import json
from pathlib import Path

import apizr
from apizr import tracking
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
from apizr.tracking.adapters import AdapterReporter
from apizr.tracking.session import TrackingError


def prove(root: Path) -> dict[str, object]:
    source = SourceView(
        reference="example.py",
        text="from sklearn.metrics import accuracy_score\naccuracy_score([1], [1])\n",
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
    return {
        "status": "passed",
        "installed_package": apizr.__file__,
        "source_digest": source.digest,
        "static_result_schema": result.schema_version,
        "sdk_run_schema": capture.record.run.schema_version,
        "source_mismatch": "refused",
        "non_finite_adapter_value": "refused",
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

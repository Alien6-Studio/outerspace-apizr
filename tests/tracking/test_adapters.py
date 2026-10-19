"""Scientific adapters report through existing SDK authority and JSON bounds."""

import pytest

from apizr import tracking
from apizr.experiments.model import EvidenceOrigin
from apizr.scientific_providers import ProducerIdentity, SDKAdapterDescriptor
from apizr.tracking.adapters import AdapterReporter
from apizr.tracking.session import TrackingError


def reporter(capabilities=("parameter", "metric", "input", "artifact")):
    return AdapterReporter(
        SDKAdapterDescriptor(
            identity=ProducerIdentity(name="sample.adapter", version="1.0"),
            capabilities=capabilities,
        )
    )


def test_reporter_records_only_through_ordinary_session(tmp_path):
    (tmp_path / "input.csv").write_text("x\n1\n")
    (tmp_path / "model.bin").write_bytes(b"opaque output bytes")
    bridge = reporter()
    with tracking.session(root=tmp_path) as capture:
        bridge.log_parameter("batch", 8)
        bridge.log_metric("accuracy", 0.9, unit="ratio")
        bridge.log_input("dataset", "input.csv")
        bridge.log_input("memory")
        bridge.log_input("remote", uri="https://example.com/data.csv")
        bridge.log_artifact("model", "model.bin", media_type="application/octet-stream")
    run = capture.record.run
    assert run.effective_parameters[0].value == 8
    assert run.metrics[0].value == 0.9
    assert run.outputs[0].digest is not None
    assert run.observed_inputs[1].origin == EvidenceOrigin.UNKNOWN
    assert not hasattr(bridge, "store") and not hasattr(bridge, "finalize")


@pytest.mark.parametrize(
    "method,args",
    [
        ("log_parameter", ("p", 1)),
        ("log_metric", ("m", 1)),
        ("log_input", ("i",)),
        ("log_artifact", ("a", "a.bin")),
    ],
)
def test_reporter_requires_session_and_declared_capability(tmp_path, method, args):
    bridge = reporter()
    with pytest.raises(TrackingError, match="tracking_no_active_session"):
        getattr(bridge, method)(*args)
    restricted = reporter(("metric",) if method != "log_metric" else ("parameter",))
    with tracking.session(root=tmp_path):
        with pytest.raises(
            TrackingError, match="tracking_adapter_capability_undeclared"
        ):
            getattr(restricted, method)(*args)


@pytest.mark.parametrize(
    "value",
    [float("nan"), 2**63, [0] * 1025, "é" * 8193, object()],
    ids=["nonfinite", "integer", "collection", "string", "opaque"],
)
def test_adapter_never_bypasses_experiment_value_validation(tmp_path, value):
    with tracking.session(root=tmp_path) as capture:
        with pytest.raises(TrackingError, match="tracking_metric_invalid"):
            reporter(("metric",)).log_metric("accuracy", value)
    assert capture.record.run.status == "failed"
    assert not capture.record.run.metrics


def test_adapter_object_is_not_traversed_pickled_or_stringified(tmp_path):
    class Opaque:
        def __repr__(self):
            raise AssertionError("opaque representation accessed")

        def __reduce__(self):
            raise AssertionError("opaque pickle accessed")

    class Adapter:
        def observe(self, value, *, reporter):
            assert isinstance(value, Opaque)
            reporter.log_metric("accuracy", 0.75)

    with tracking.session(root=tmp_path) as capture:
        Adapter().observe(Opaque(), reporter=reporter(("metric",)))
    assert capture.record.run.metrics[0].value == 0.75

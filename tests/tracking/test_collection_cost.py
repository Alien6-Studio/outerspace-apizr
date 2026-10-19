"""Capture keeps exact admission bounds without eager imports or JSON copies."""

import hashlib
import json
import math
import os
import random
import struct
import subprocess
import sys

import pytest

from apizr import tracking
from apizr.experiments import EvidenceOrigin, inputs, outputs
from apizr.experiments.capture_model import CallParameter
from apizr.experiments.model import (
    ExperimentValue,
    InputArtifact,
    Metric,
    OutputArtifact,
    Parameter,
)
from apizr.tracking.budget import capture_size


def test_import_and_suppressed_logging_do_not_load_capture_domains():
    code = """
import os, sys
import apizr.tracking as tracking
os.environ['APIZR_SERVED_PROCESS'] = '1'
tracking.log_parameter('unused', object())
tracking.log_metric('unused', object())
@tracking.experiment(parameters=['value'])
def compute(value):
    return value
assert compute(1) == 1
assert not any(name.startswith(('apizr.experiments', 'apizr.plugins', 'pydantic', 'asyncio', 'IPython')) for name in sys.modules)
"""
    subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        check=True,
        capture_output=True,
        timeout=15,
    )


def test_all_public_exports_survive_explicit_session_module_import(tmp_path):
    import importlib

    module = importlib.import_module("apizr.tracking.session")
    assert callable(tracking.session)
    assert tracking.TrackingSession is module.TrackingSession
    with tracking.session(root=tmp_path) as capture:
        tracking.log_metric("score", 1)
    assert capture.record.run.metrics[0].value == 1


def test_logging_does_not_serialize_whole_values_or_observations(tmp_path, monkeypatch):
    (tmp_path / "data.bin").write_bytes(b"observed")

    def forbidden(*args, **kwargs):
        raise AssertionError("logging serialized an observation")

    with tracking.session(root=tmp_path) as capture:
        with monkeypatch.context() as guard:
            guard.setattr(ExperimentValue, "model_dump_json", forbidden)
            guard.setattr(json, "dumps", forbidden)
            tracking.log_parameter("schedule", {"steps": [1, 2, 3], "tag": 'é\\"\n'})
            tracking.log_metric("score", 0.75)
            tracking.log_input("data", "data.bin")
            tracking.log_artifact("output", "data.bin")
    assert capture.record.run.status == "success"
    assert capture.record.run.effective_parameters[0].value["steps"] == (1, 2, 3)


def test_digest_once_per_observation_and_never_cached_by_file_metadata(
    tmp_path, monkeypatch
):
    path = tmp_path / "data.bin"
    path.write_bytes(b"first")
    calls = []
    original = inputs.fingerprint_file

    def observed(root, reference, limit):
        result = original(root, reference, limit)
        calls.append((reference, result[0]))
        return result

    monkeypatch.setattr(inputs, "fingerprint_file", observed)
    monkeypatch.setattr(outputs, "fingerprint_file", observed)
    with tracking.session(root=tmp_path) as capture:
        tracking.log_input("before", "data.bin")
        stamp = path.stat()
        path.write_bytes(b"later")  # Same path and size, different content.
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        assert (path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns) == (
            stamp.st_ino,
            stamp.st_size,
            stamp.st_mtime_ns,
        )
        tracking.log_input("after", "data.bin")
        tracking.log_artifact("model", "data.bin")
        at_logging = tuple(calls)
        path.write_bytes(
            b"third"
        )  # Finalization must retain the explicit observations.
    assert tuple(calls) == at_logging  # Finalization serializes retained observations.
    assert [digest for _, digest in calls] == [
        hashlib.sha256(data).hexdigest() for data in (b"first", b"later", b"later")
    ]
    assert {item.name: item.digest for item in capture.record.run.observed_inputs} == {
        "before": calls[0][1],
        "after": calls[1][1],
    }
    assert capture.record.run.outputs[0].digest == calls[2][1]


def test_byte_accounting_matches_installed_serializer_for_admitted_evidence():
    randomizer = random.Random(322)
    numbers = [0.0, -0.0, 1e-7, 1e20, 1.7976931348623157e308, -(2**63), 2**63 - 1]
    while len(numbers) < 100:
        number = struct.unpack("!d", randomizer.randbytes(8))[0]
        if math.isfinite(number):
            numbers.append(number)
    values = [
        None,
        True,
        False,
        'é😀\n\x01\\"',
        "".join(chr(code) for code in range(32)) + "\u2028\u2029\x7f\x80",
        {"nested": [1, False, None, 1e-7]},
        *numbers,
    ]
    evidence = [
        Parameter(name="value", value=value, origin=EvidenceOrigin.RUNTIME)
        for value in values
    ]
    evidence += [
        Metric(
            name="value",
            value=value,
            unit="é" if type(value) in (int, float) else None,
            origin=EvidenceOrigin.RUNTIME,
        )
        for value in values
    ]
    evidence += [
        CallParameter(
            name="value",
            value=value,
            value_type="builtins.object",
            origin=EvidenceOrigin.RUNTIME,
        )
        for value in values
    ]
    evidence += [
        InputArtifact(name="unknown", origin=EvidenceOrigin.UNKNOWN),
        InputArtifact(
            name="remote",
            uri="https://example.org/data.csv",
            origin=EvidenceOrigin.STATIC,
            content_origin=EvidenceOrigin.UNKNOWN,
            format_hint="csv",
        ),
        InputArtifact(
            name="selected",
            reference="data.bin",
            digest="a" * 64,
            size=5,
            origin=EvidenceOrigin.RUNTIME,
            content_origin=EvidenceOrigin.RUNTIME,
        ),
        OutputArtifact(
            name="output",
            reference="model.bin",
            digest="b" * 64,
            size=5,
            origin=EvidenceOrigin.RUNTIME,
        ),
    ]
    for item in evidence:
        assert capture_size(item) == len(item.model_dump_json().encode("utf-8")), item


def test_capture_boundary_accepts_exact_bytes_and_refuses_next_item(
    tmp_path, monkeypatch
):
    import importlib

    module = importlib.import_module("apizr.tracking.session")
    item = Metric(
        name="score", value={"curve": [0.25, 0.5]}, origin=EvidenceOrigin.RUNTIME
    )
    monkeypatch.setattr(
        module, "MAX_CAPTURE_BYTES", len(item.model_dump_json().encode("utf-8"))
    )
    with tracking.session(root=tmp_path) as capture:
        tracking.log_metric("score", {"curve": [0.25, 0.5]})
        with pytest.raises(tracking.TrackingError, match="tracking_capture_limit"):
            tracking.log_metric("another", 1)
    assert capture.record.run.status == "failed"
    assert len(capture.record.run.metrics) == 1


def test_decorated_call_budget_is_checked_before_business_code(tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module("apizr.tracking.session")
    item = CallParameter(name="value", value="é", origin=EvidenceOrigin.RUNTIME)
    monkeypatch.setattr(module, "MAX_CAPTURE_BYTES", capture_size(item) - 1)
    executed = False

    @tracking.experiment(parameters=["value"], root=tmp_path)
    def compute(value):
        nonlocal executed
        executed = True

    with pytest.raises(tracking.TrackingError, match="tracking_capture_limit"):
        compute("é")
    assert not executed


def test_counter_refuses_an_unadmitted_object_without_formatting_it():
    class BusinessObject:
        def __repr__(self):
            raise AssertionError("counter formatted a business object")

    forged = Parameter.model_construct(
        name="value", value=BusinessObject(), origin=EvidenceOrigin.RUNTIME
    )
    with pytest.raises(TypeError, match="tracking_budget_requires_admitted_value"):
        capture_size(forged)

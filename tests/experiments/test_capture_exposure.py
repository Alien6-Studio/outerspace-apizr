"""Versioned SDK exposure retains unknown provenance and all serving authorities."""

import json
import zipfile
from importlib.metadata import version

import pytest

from apizr import tracking
from apizr.experiments import SourceEvidence
from apizr.experiments.exposure import expose_run
from apizr.experiments.exposure_model import (
    ExperimentExposureBinding,
    ExperimentExposureBindingV2,
    exposure_bytes,
    validate_exposure_binding,
)
from apizr.experiments.serialization import plan_digest, run_digest
from apizr.experiments.store import RunRecordV2
from apizr.repository_interfaces.model import RepositoryInterface

from .exposure_support import authority, project


@pytest.fixture
def case(tmp_path):
    path = project(tmp_path / "project")
    with tracking.session(root=path.parent, source=path.name) as capture:
        tracking.log_artifact("model", "model.json")
    return path, capture.record


def compile_case(case, **kwargs):
    path, record = case
    return expose_run(
        record,
        path.parent,
        **{
            "capability": "python:serving:predict",
            "interface": "rest",
            "operator_policy": authority(path.parent),
            "artifacts": ("model",),
            **kwargs,
        },
    )


def changed_record(record, **changes):
    plan = record.plan.model_copy(
        update={k: v for k, v in changes.items() if k in {"subject", "capture"}}
    )
    run = record.run.model_copy(update={**changes, "plan_digest": plan_digest(plan)})
    return RunRecordV2(
        plan=plan, run=run, plan_digest=plan_digest(plan), run_digest=run_digest(run)
    )


@pytest.mark.parametrize("interface", ["rest", "mcp"])
def test_sdk_run_exposes_exact_observed_source_without_rewriting_history(
    case, interface
):
    path, record = case
    original = record.model_dump_json()
    result = compile_case(case, interface=interface)
    binding = result.result.binding
    assert isinstance(binding, ExperimentExposureBindingV2)
    assert binding.observed_source == record.run.subject
    assert binding.observed_source.identity.module is None
    assert binding.source.module == "serving"
    assert binding.source.digest == record.run.subject.identity.digest
    assert binding.capture == record.run.capture
    assert binding.capture.function.source_digest is None
    assert record.model_dump_json() == original
    assert (
        ExperimentExposureBindingV2.model_validate_json(exposure_bytes(binding))
        == binding
    )
    assert (
        json.loads(result.bundle["experiment-exposure.json"])["schema_version"]
        == "apizr.experiment-exposure/v2"
    )
    assert (
        b"APIZR_SERVED_PROCESS"
        not in result.bundle["app.py" if interface == "rest" else "server.py"]
    )
    assert b"outerspace-apizr" not in result.bundle["requirements.txt"]
    assert not (path.parent / "training-executed").exists()


def test_unknown_sdk_source_is_refused_before_source_admission(case, monkeypatch):
    record = changed_record(case[1], subject=SourceEvidence())
    monkeypatch.setattr(
        "apizr.experiments.exposure.open_analysis_root",
        lambda *a: pytest.fail("unknown source read"),
    )
    with pytest.raises(ValueError, match="run_source_unknown"):
        compile_case((case[0], record))


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_failed_sdk_capture_never_becomes_serving(case, monkeypatch, status):
    monkeypatch.setattr(
        "apizr.experiments.exposure.open_analysis_root",
        lambda *a: pytest.fail("failed capture read"),
    )
    with pytest.raises(ValueError, match="run_not_successful"):
        compile_case((case[0], changed_record(case[1], status=status)))


def test_sdk_notebook_requires_recorded_executable_evidence(case):
    identity = case[1].run.subject.identity.model_copy(update={"kind": "notebook"})
    record = changed_record(
        case[1], subject=SourceEvidence(identity=identity, origin="runtime")
    )
    with pytest.raises(ValueError, match="run_notebook_executable_unknown"):
        compile_case((case[0], record))


def test_known_sdk_module_cannot_be_replaced_by_selected_module(case):
    identity = case[1].run.subject.identity.model_copy(update={"module": "other"})
    record = changed_record(
        case[1], subject=SourceEvidence(identity=identity, origin="runtime")
    )
    with pytest.raises(ValueError, match="capability_not_in_run_source"):
        compile_case((case[0], record))


def test_sdk_source_and_artifact_changes_still_refuse(case):
    path, _ = case
    content = path.read_bytes()
    path.write_bytes(content + b"\n")
    with pytest.raises(ValueError, match="run_source_changed"):
        compile_case(case)
    path.write_bytes(content)
    (path.parent / "model.json").write_text('{"multiplier": 4}')
    with pytest.raises(ValueError, match="run_artifact_changed"):
        compile_case(case)


def test_sdk_capture_does_not_grant_operator_permission(case):
    from apizr.workspace.operator_policy import AuthorizationDenied

    with pytest.raises(AuthorizationDenied):
        compile_case(case, operator_policy=None)


@pytest.mark.parametrize("field", ["observed_source", "capture", "source"])
def test_portable_binding_cannot_swap_capture_or_observed_source(case, field):
    result = compile_case(case)
    binding = result.result.binding
    replacement = {
        "observed_source": SourceEvidence(),
        "capture": binding.capture.model_copy(update={"producer_version": "different"}),
        "source": binding.source.model_copy(update={"digest": "a" * 64}),
    }[field]
    forged = binding.model_copy(update={field: replacement})
    contract = RepositoryInterface.model_validate_json(
        result.bundle["repository-interface.json"]
    )
    with pytest.raises(ValueError, match="experiment_capture_binding_mismatch"):
        validate_exposure_binding(
            forged, case[1], contract, result.prepared.plan, result.prepared.application
        )


def test_v1_binding_cannot_describe_a_v2_record(case):
    result = compile_case(case)
    fields = result.result.binding.model_dump(
        exclude={"observed_source", "capture", "schema_version"}
    )
    binding = ExperimentExposureBinding.model_validate(fields)
    contract = RepositoryInterface.model_validate_json(
        result.bundle["repository-interface.json"]
    )
    with pytest.raises(ValueError, match="experiment_capture_binding_mismatch"):
        validate_exposure_binding(
            binding,
            case[1],
            contract,
            result.prepared.plan,
            result.prepared.application,
        )


def test_v2_binding_requires_application_presence(case):
    result = compile_case(case)
    with pytest.raises(ValueError, match="experiment_application_binding_missing"):
        ExperimentExposureBindingV2.model_validate(
            result.result.binding.model_dump() | {"application_inputs_digest": None}
        )


def test_derived_binding_revalidates_copied_digests(case):
    result = compile_case(case)
    forged = result.result.binding.model_copy(
        update={
            "catalog_digest": result.result.binding.catalog_digest.model_copy(
                update={"value": "bad"}
            )
        }
    )
    with pytest.raises(ValueError):
        exposure_bytes(forged)


def test_actual_cli_exposes_a_shared_sdk_record(case, tmp_path, capfd):
    from apizr.cli.commands.experiment import main

    operator = tmp_path / "operator.json"
    operator.write_text(authority(case[0].parent).model_dump_json(by_alias=True))
    output = tmp_path / "rest"
    assert (
        main(
            [
                "expose",
                case[1].run_digest,
                "--root",
                str(case[0].parent),
                "--operator-policy",
                str(operator),
                "--capability",
                "python:serving:predict",
                "--interface",
                "rest",
                "--artifact",
                "model",
                "--output-dir",
                str(output),
                "--format",
                "json",
            ]
        )
        == 0
    )
    result = json.loads(capfd.readouterr().out)
    assert result["binding"]["schema_version"] == "apizr.experiment-exposure/v2"
    assert result["binding"]["run_digest"] == case[1].run_digest


def test_instrumented_service_suppresses_capture_before_source_import(case, tmp_path):
    import httpx
    from governed.helpers import SERVER, http_server

    from apizr.repository_interfaces.output import write_bundle

    path, _ = case
    source = "import apizr.tracking as sdk\n" + path.read_text()
    source = source.replace(
        "def predict(", '@sdk.experiment(parameters=["request"])\ndef predict('
    )
    source = source.replace(
        '    return {"predictions":',
        '    sdk.log_metric("served_value", request["value"])\n    return {"predictions":',
    )
    path.write_text(source)
    with tracking.session(
        root=path.parent, source=path.name, distributions=("outerspace-apizr",)
    ) as capture:
        tracking.log_artifact("model", "model.json")
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    current = version("outerspace-apizr")
    wheel = wheels / f"outerspace_apizr-{current}-py3-none-any.whl"
    info = f"outerspace_apizr-{current}.dist-info"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"{info}/METADATA",
            f"Metadata-Version: 2.3\nName: outerspace-apizr\nVersion: {current}\n\n",
        )
        archive.writestr(f"{info}/WHEEL", "Wheel-Version: 1.0\nTag: py3-none-any\n")
        archive.writestr(f"{info}/RECORD", "")
        archive.writestr("apizr/__init__.py", "")
        archive.writestr(
            "apizr/tracking/__init__.py",
            "raise AssertionError('compiler imported provider')\n",
        )
    result = compile_case(
        (path, capture.record),
        dependencies=("outerspace-apizr",),
        dependency_wheelhouse=wheels,
        allow_conditional=True,
    )
    assert result.result.binding.dependencies == (f"outerspace-apizr=={current}",)
    root = tmp_path / "service"
    write_bundle(root, result.bundle)
    server = SERVER.replace(
        "root=Path(sys.argv[1]).resolve()",
        "root=Path(sys.argv[1]).resolve()\nsys.path.insert(0,str(root))",
    )
    with (
        http_server(root, "rest", server=server) as (url, _),
        httpx.Client(base_url=url) as client,
    ):
        for value in (4, 5):
            response = client.post(
                "/capabilities/serving.predict", json={"request": {"value": value}}
            )
            assert response.status_code == 200
            assert response.json() == {"predictions": [[value * 3, True]]}
    assert not list(root.rglob(".apizr"))

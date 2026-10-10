"""Explicit Run admission, unchanged repository authority and portable binding."""

import json
import shutil
from dataclasses import replace

import pytest

from apizr.capabilities.model import Digest
from apizr.experiments.exposure import expose_run
from apizr.experiments.exposure_model import (
    EXPOSURE_FILE,
    ExperimentExposureBinding,
    exposure_bytes,
    validate_exposure_binding,
)
from apizr.repository_interfaces.evidence import export_evidence, verify_evidence
from apizr.repository_interfaces.model import RepositoryInterface
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_interfaces.runtime import validate_bundle

from .exposure_support import authority, changed_record, project, record_for


@pytest.fixture
def case(tmp_path):
    path = project(tmp_path / "project")
    return path, record_for(path)


def compile_case(case, **kwargs):
    path, record = case
    return expose_run(
        record,
        path.parent,
        **(
            {
                "capability": "python:serving:predict",
                "interface": "rest",
                "operator_policy": authority(path.parent),
                "artifacts": ("model",),
            }
            | kwargs
        ),
    )


@pytest.mark.parametrize("interface", ["rest", "mcp"])
def test_existing_pipeline_binding_and_selection(case, tmp_path, interface):
    result = compile_case(case, interface=interface, dependencies=("Example_Package",))
    binding = result.result.binding
    assert (
        binding.run_digest == case[1].run_digest
        and binding.plan_digest == case[1].plan_digest
    )
    assert binding.source == case[1].run.subject
    assert binding.dependencies == ("example-package==1.2.3",)
    assert [o.name for o in binding.outputs] == ["model"]
    assert result.bundle["application-requirements.txt"] == b"example-package==1.2.3\n"
    assert (
        "source/model.json" in result.bundle
        and "source/debug.json" not in result.bundle
    )
    assert not result.prepared.evidence.graph.complete
    assert result.prepared.readiness.exit_code != 0
    assert len(result.prepared.plan.capabilities) == 1
    assert (
        result.prepared.plan.capabilities[0].capability_id == "python:serving:predict"
    )
    contract = RepositoryInterface.model_validate_json(
        result.bundle["repository-interface.json"]
    )
    assert (
        validate_exposure_binding(
            binding,
            case[1],
            contract,
            result.prepared.plan,
            result.prepared.application,
        )
        == binding
    )
    assert (
        ExperimentExposureBinding.model_validate_json(exposure_bytes(binding))
        == binding
    )
    assert (
        json.loads(result.bundle[f"apizr-repository-{interface}.json"])["artifacts"][
            EXPOSURE_FILE
        ]
        == Digest.of_bytes(exposure_bytes(binding)).model_dump()
    )
    bundle, evidence = tmp_path / "bundle", tmp_path / "evidence"
    write_bundle(bundle, result.bundle)
    export_evidence(bundle, evidence, interface=interface)
    assert (evidence / EXPOSURE_FILE).is_file()
    assert (evidence / EXPOSURE_FILE).read_bytes() == result.bundle[EXPOSURE_FILE]
    shutil.rmtree(bundle)
    verify_evidence(
        evidence, interface=interface, expected=result.result.bundle_manifest_digest
    )
    assert not (evidence / "source/model.json").exists()
    (evidence / EXPOSURE_FILE).write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="digest"):
        verify_evidence(
            evidence, interface=interface, expected=result.result.bundle_manifest_digest
        )


@pytest.mark.parametrize("notebook", [False, True])
def test_relocation_and_source_output_change_properties(tmp_path, notebook):
    path = project(tmp_path / "a", notebook=notebook)
    case = path, record_for(path)
    original = compile_case(case)
    shutil.copytree(path.parent, tmp_path / "b")
    moved = compile_case((tmp_path / "b" / path.name, case[1]))
    assert original.bundle == moved.bundle
    raw = path.read_bytes()
    path.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="run_source_changed"):
        compile_case(case)
    path.write_bytes(raw)
    model = path.parent / "model.json"
    data = model.read_bytes()
    model.write_bytes(data.replace(b"3", b"4"))
    with pytest.raises(ValueError, match="run_artifact_changed"):
        compile_case(case)
    swapped = record_for(path)
    assert compile_case((path, swapped)).result != original.result
    model.write_bytes(data)
    assert compile_case(case).bundle == original.bundle


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_unsuccessful_run_refused_before_io(case, monkeypatch, status):
    def forbidden(*args, **kwargs):
        raise AssertionError("source read for unsuccessful Run")

    monkeypatch.setattr("apizr.experiments.exposure.open_analysis_root", forbidden)
    with pytest.raises(ValueError, match="run_not_successful"):
        compile_case((case[0], changed_record(case[1], status=status)))


@pytest.mark.parametrize(
    "capability",
    [
        "python:admin:admin",
        "python:helper:_predict",
        "predict",
        "python:serving:missing",
    ],
)
def test_exact_run_source_membership(case, capability):
    with pytest.raises(ValueError):
        compile_case(case, capability=capability)


def test_no_implicit_resources_or_dependencies(case):
    result = compile_case(case, artifacts=())
    assert not result.result.binding.outputs and not result.result.binding.dependencies
    assert result.prepared.application is None
    assert "source/model.json" not in result.bundle
    assert "application-requirements.txt" not in result.bundle


def test_operator_authority_not_inferred_from_run(case):
    from apizr.workspace.operator_policy import AuthorizationDenied

    with pytest.raises(AuthorizationDenied):
        compile_case(case, operator_policy=None)


@pytest.mark.parametrize(
    "target",
    [
        EXPOSURE_FILE,
        "source/model.json",
        "repository-interface.json",
        "exposure-plan.json",
    ],
)
def test_bundle_integrity_detects_tampering(case, tmp_path, target):
    result = compile_case(case)
    bundle = tmp_path / "bundle"
    write_bundle(bundle, result.bundle)
    validate_bundle(bundle, "rest")
    (bundle / target).write_bytes((bundle / target).read_bytes() + b" ")
    with pytest.raises(ValueError, match="digest"):
        validate_bundle(bundle, "rest")


def test_existing_governed_resource_refusal(case):
    from apizr.execution.policy import ExecutionPolicy
    from apizr.workspace.compiler import render_bundle

    result = compile_case(case)
    with pytest.raises(ValueError):
        render_bundle(
            replace(result.prepared),
            interface="rest",
            execution_policy=ExecutionPolicy(),
        )

"""Adversarial selections and integrity checks before atomic bundle publication."""

import os
from dataclasses import replace

import pytest

from apizr.capabilities.model import Digest
from apizr.experiments._files import FileFailure
from apizr.experiments.exposure_model import (
    selected_dependencies,
    validate_exposure_binding,
)
from apizr.experiments.model import EnvironmentEvidence, EvidenceOrigin, PackageEvidence
from apizr.exposure import ExposureRefused
from apizr.repository import ScanPolicy
from apizr.repository_interfaces.model import RepositoryInterface
from apizr.repository_readiness import RepositoryReadinessPolicy

from .exposure_support import changed_record, project, record_for
from .test_exposure import compile_case


@pytest.fixture
def case(tmp_path):
    path = project(tmp_path / "project")
    return path, record_for(path)


@pytest.mark.parametrize("selection", [("missing",), ("model", "model")])
def test_invalid_artifact_selection(case, selection):
    with pytest.raises(ValueError, match="run_artifact_"):
        compile_case(case, artifacts=selection)


@pytest.mark.parametrize(
    "fault",
    [
        "reference",
        "digest",
        "size",
        "missing",
        "symlink",
        "parent-symlink",
        "fifo",
        "directory",
        "too-large",
    ],
)
def test_selected_output_identity_and_safe_open(case, fault):
    path, record = case
    output = next(o for o in record.run.outputs if o.name == "model")
    model = path.parent / output.reference
    if fault in {"reference", "digest", "size"}:
        changes = (
            {"reference": None}
            if fault == "reference"
            else {"digest": "0" * 64}
            if fault == "digest"
            else {"size": output.size + 1}
        )
        output = output.model_copy(update=changes)
        record = changed_record(record, outputs=(output,))
    elif fault == "too-large":
        with model.open("wb") as stream:
            stream.truncate(16 * 1024 * 1024 + 1)
    elif fault == "parent-symlink":
        (path.parent / "link").symlink_to(path.parent, target_is_directory=True)
        record = changed_record(
            record,
            outputs=(output.model_copy(update={"reference": "link/model.json"}),),
        )
    else:
        model.unlink()
        if fault == "symlink":
            model.symlink_to(path.parent / "debug.json")
        elif fault == "fifo":
            os.mkfifo(model)
        elif fault == "directory":
            model.mkdir()
    with pytest.raises(ValueError, match="run_artifact_"):
        compile_case((path, record))


def test_changed_during_read_and_replaced_between_captures(case, monkeypatch):
    def changing(*args):
        raise FileFailure("changed_during_read")

    with monkeypatch.context() as patch:
        patch.setattr("apizr.experiments.exposure.fingerprint_file", changing)
        with pytest.raises(ValueError, match="run_artifact_changed_during_read"):
            compile_case(case)
    monkeypatch.setattr(
        "apizr.experiments.exposure.capture_resources",
        lambda *args: {"model.json": b"CHANGED"},
    )
    with pytest.raises(ValueError, match="run_artifact_changed"):
        compile_case(case)


@pytest.mark.parametrize(
    "names",
    [
        ("unknown",),
        ("example-package>=1",),
        ("https://example.com/a.whl",),
        ("example-package", "Example_Package"),
    ],
)
def test_dependency_selectors(case, names):
    with pytest.raises(ValueError, match="run_dependency_"):
        compile_case(case, dependencies=names)


@pytest.mark.parametrize(
    "environment",
    [
        None,
        EnvironmentEvidence(),
        EnvironmentEvidence(
            packages=(
                PackageEvidence(
                    name="example-package", version=None, origin=EvidenceOrigin.UNKNOWN
                ),
            )
        ),
    ],
)
def test_unobserved_dependency_never_falls_back(case, environment, monkeypatch):
    import importlib.metadata

    def forbidden(*args, **kwargs):
        pytest.fail("queried current environment")

    monkeypatch.setattr(importlib.metadata, "version", forbidden)
    record = changed_record(case[1], environment=environment)
    with pytest.raises(ValueError, match="run_dependency_unobserved"):
        compile_case((case[0], record), dependencies=("example-package",))


def test_dependency_count_and_unrepresentable_version(case):
    packages = tuple(
        PackageEvidence(
            name=f"package-{index}", version="1", origin=EvidenceOrigin.RUNTIME
        )
        for index in range(129)
    )
    record = changed_record(case[1], environment=EnvironmentEvidence(packages=packages))
    with pytest.raises(ValueError, match="run_dependency_invalid"):
        selected_dependencies(record, tuple(p.name for p in packages))
    record = changed_record(
        case[1],
        environment=EnvironmentEvidence(
            packages=(
                PackageEvidence(
                    name="package",
                    version="not-a-version",
                    origin=EvidenceOrigin.RUNTIME,
                ),
            )
        ),
    )
    with pytest.raises(ValueError, match="run_dependency_invalid"):
        selected_dependencies(record, ("package",))


def test_required_dependency_ambiguity_refuses(case):
    (case[0].parent / "helper.py").write_text(
        "def _predict(x): return x\ndef _predict(x): return x\n"
    )
    with pytest.raises(ExposureRefused):
        compile_case(case)


def test_changed_source_refuses_before_repository_planning(case, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("changed source entered repository pipeline")

    monkeypatch.setattr("apizr.experiments.exposure.analyze_repository", forbidden)
    case[0].write_bytes(case[0].read_bytes() + b" ")
    with pytest.raises(ValueError, match="run_source_changed"):
        compile_case(case)


def test_unrelated_capability_refuses_before_repository_planning(case, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unrelated capability entered repository pipeline")

    monkeypatch.setattr("apizr.experiments.exposure.analyze_repository", forbidden)
    with pytest.raises(ValueError, match="capability_not_in_run_source"):
        compile_case(case, capability="python:admin:admin")


def test_conditional_and_explicit_execution_policy_are_not_waived(case):
    conditional = RepositoryReadinessPolicy.model_validate(
        {
            "effects": {"require_known": ("network",)},
            "execution": {"modes": ("direct",)},
        }
    )
    with pytest.raises(ExposureRefused):
        compile_case(case, readiness_policy=conditional)
    assert compile_case(case, readiness_policy=conditional, allow_conditional=True)
    with pytest.raises(ExposureRefused):
        compile_case(case, readiness_policy=RepositoryReadinessPolicy())


@pytest.mark.parametrize("fault", ["path", "module", "count", "bytes", "transformed"])
def test_notebook_admission_and_bounds(tmp_path, fault):
    path = project(tmp_path / "project", notebook=True)
    record = record_for(path)
    options = {}
    if fault == "path":
        (path.parent / "serving.py").write_text("def other(): pass")
    elif fault == "module":
        (path.parent / "serving").mkdir()
        (path.parent / "serving/__init__.py").write_text("def other(): pass")
    elif fault == "count":
        options["scan_policy"] = ScanPolicy(max_source_files=3)
    elif fault == "bytes":
        options["scan_policy"] = ScanPolicy(max_total_bytes=1)
    else:
        from apizr.experiments.serialization import plan_digest, run_digest
        from apizr.experiments.store import RunRecord

        subject = record.run.subject.model_copy(update={"executable_digest": "0" * 64})
        plan = record.plan.model_copy(update={"subject": subject})
        run = record.run.model_copy(
            update={"subject": subject, "plan_digest": plan_digest(plan)}
        )
        record = RunRecord(
            plan=plan,
            run=run,
            plan_digest=plan_digest(plan),
            run_digest=run_digest(run),
        )
    with pytest.raises(ValueError):
        compile_case((path, record), **options)


@pytest.mark.parametrize(
    "field",
    [
        "run_digest",
        "plan_digest",
        "repository_digest",
        "catalog_digest",
        "graph_digest",
        "repository_readiness_digest",
        "exposure_plan_digest",
        "repository_interface_digest",
        "application_inputs_digest",
        "capability",
        "interface",
        "source",
        "outputs",
        "dependencies",
    ],
)
def test_pure_cross_binding_verifier_rejects_swaps(case, field):
    result = compile_case(case, dependencies=("example-package",))
    binding = result.result.binding
    if field in {"run_digest", "plan_digest"}:
        value = "0" * 64
    elif field.endswith("digest"):
        value = Digest(value="0" * 64)
    elif field == "capability":
        value = "python:admin:admin"
    elif field == "interface":
        value = "mcp"
    elif field == "source":
        value = binding.source.model_copy(update={"digest": "0" * 64})
    elif field == "outputs":
        value = (binding.outputs[0].model_copy(update={"digest": "0" * 64}),)
    else:
        value = ("example-package==9.9.9",)
    contract = RepositoryInterface.model_validate_json(
        result.bundle["repository-interface.json"]
    )
    with pytest.raises(ValueError):
        validate_exposure_binding(
            binding.model_copy(update={field: value}),
            case[1],
            contract,
            result.prepared.plan,
            result.prepared.application,
        )


def test_governed_oci_resources_remain_refused(case):
    from apizr.oci.model import ExecutionPolicyV2, RuntimeImage
    from apizr.workspace.compiler import render_bundle

    result = compile_case(case)
    with pytest.raises(ValueError):
        render_bundle(
            replace(result.prepared),
            interface="rest",
            execution_policy=ExecutionPolicyV2(),
            runtime_image=RuntimeImage(
                image="sha256:" + "a" * 64, platform="linux/amd64"
            ),
        )


def test_no_deserialization_execution_resolution_or_network(case, monkeypatch):
    import importlib.metadata
    import pickle
    import socket
    import subprocess

    def forbidden(*args, **kwargs):
        pytest.fail("bridge attempted execution, deserialization or resolution")

    original = importlib.metadata.version

    def version(name):
        assert name == "outerspace-apizr"  # Existing generator provenance only.
        return original(name)

    monkeypatch.setattr(importlib.metadata, "version", version)
    monkeypatch.setattr(pickle, "load", forbidden)
    monkeypatch.setattr(pickle, "loads", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr("apizr.experiments.runner.run_experiment", forbidden)
    assert compile_case(case, dependencies=("example-package",))


def test_unknown_recorded_size_is_not_invented(case):
    path, record = case
    outputs = tuple(o.model_copy(update={"size": None}) for o in record.run.outputs)
    result = compile_case((path, changed_record(record, outputs=outputs)))
    assert result.result.binding.outputs[0].size is None
    assert result.prepared.application.resources[0].size == len(
        result.bundle["source/model.json"]
    )


def test_application_limits_and_rejected_paths(case):
    from hashlib import sha256

    from apizr.experiments.model import OutputArtifact

    path, record = case
    output = record.run.outputs[0]
    for references in ((".hidden",), tuple(f"resource-{i}" for i in range(129))):
        outputs = tuple(
            output.model_copy(update={"name": str(i), "reference": reference})
            for i, reference in enumerate(references)
        )
        with pytest.raises(ValueError):
            compile_case(
                (path, changed_record(record, outputs=outputs)),
                artifacts=tuple(o.name for o in outputs),
            )
    data = b"x" * (12 * 1024 * 1024)
    outputs = []
    for name in ("a", "b", "c"):
        (path.parent / name).write_bytes(data)
        outputs.append(
            OutputArtifact(
                name=name,
                reference=name,
                digest=sha256(data).hexdigest(),
                size=len(data),
                origin=EvidenceOrigin.RUNTIME,
            )
        )
    with pytest.raises(ValueError, match="aggregate"):
        compile_case(
            (path, changed_record(record, outputs=tuple(outputs))),
            artifacts=("a", "b", "c"),
        )


def test_notebook_rechecks_retained_transformation_and_scan_roots(
    tmp_path, monkeypatch
):
    from apizr.experiments import exposure

    path = project(tmp_path / "project", notebook=True)
    record = record_for(path)
    with monkeypatch.context() as patch:
        original = exposure.read_regular
        patch.setattr(
            exposure, "read_regular", lambda path, limit: original(path, limit) + b" "
        )
        with pytest.raises(ValueError, match="run_source_changed"):
            compile_case((path, record))
    with pytest.raises(ValueError, match="notebook_source_limit"):
        compile_case((path, record), scan_policy=ScanPolicy(max_file_bytes=1))
    nested = path.parent / "src"
    nested.mkdir()
    for name in ("helper.py", "unrelated.py", "admin.py"):
        (path.parent / name).rename(nested / name)
    result = compile_case((path, record), scan_policy=ScanPolicy(source_roots=("src",)))
    assert "src/serving.py" in result.prepared.evidence.sources


def test_binding_presence_and_independent_application_checks(case):
    from apizr.repository.serialization import canonical_bytes

    result = compile_case(case)
    binding = result.result.binding
    contract = RepositoryInterface.model_validate_json(
        result.bundle["repository-interface.json"]
    )
    plan, application = result.prepared.plan, result.prepared.application
    with pytest.raises(ValueError, match="application_binding_missing"):
        type(binding).model_validate(
            binding.model_copy(update={"application_inputs_digest": None})
        )
    with pytest.raises(ValueError, match="run_not_successful"):
        validate_exposure_binding(
            binding,
            changed_record(case[1], status="failed"),
            contract,
            plan,
            application,
        )
    source = next(s for s in contract.sources if s.module == "serving")
    changed = contract.model_copy(
        update={
            "sources": tuple(
                s.model_copy(update={"source_digest": Digest(value="0" * 64)})
                if s == source
                else s
                for s in contract.sources
            )
        }
    )
    swapped = binding.model_copy(
        update={
            "repository_interface_digest": Digest.of_bytes(canonical_bytes(changed))
        }
    )
    with pytest.raises(ValueError, match="source_binding_mismatch"):
        validate_exposure_binding(swapped, case[1], changed, plan, application)
    for fault in ("selection", "digest", "size"):
        resources = (
            ()
            if fault == "selection"
            else (
                application.resources[0].model_copy(
                    update={"digest": Digest(value="0" * 64)}
                    if fault == "digest"
                    else {"size": 0}
                ),
            )
        )
        changed_application = application.model_copy(update={"resources": resources})
        changed_contract = contract.model_copy(
            update={"application": changed_application}
        )
        swapped = binding.model_copy(
            update={
                "application_inputs_digest": Digest.of_bytes(
                    canonical_bytes(changed_application)
                ),
                "repository_interface_digest": Digest.of_bytes(
                    canonical_bytes(changed_contract)
                ),
            }
        )
        with pytest.raises(ValueError, match="binding_mismatch"):
            validate_exposure_binding(
                swapped, case[1], changed_contract, plan, changed_application
            )


def test_binding_serialization_revalidates_nested_digest_objects(case):
    from apizr.experiments.exposure_model import exposure_bytes

    binding = compile_case(case).result.binding
    forged = binding.catalog_digest.model_copy(
        update={"algorithm": "md5", "value": "invalid"}
    )
    with pytest.raises(ValueError):
        exposure_bytes(binding.model_copy(update={"catalog_digest": forged}))

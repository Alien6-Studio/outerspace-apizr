"""Wheel membership is explicit provider evidence, never executable readiness."""

import json
import zipfile
from pathlib import Path

import pytest

from apizr.capabilities.model import Digest
from apizr.contracts.application import ApplicationInputs
from apizr.exposure import ExposurePolicy, ExposureRefused, plan_exposure
from apizr.graph import build_graph
from apizr.repository import scan_sources
from apizr.repository_interfaces.planner import BundleRefused, plan_repository_interface
from apizr.repository_readiness import RepositoryReadinessPolicy, assess_repository
from apizr.repository_readiness.serialization import report_bytes
from apizr.workspace.application_dependencies import capture_dependency_wheels


def wheel(root: Path, *, package="learner", version="1.2", members=None):
    path = root / f"{package}-{version}-py3-none-any.whl"
    info = f"{package}-{version}.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{info}/METADATA",
            f"Metadata-Version: 2.3\nName: {package}\nVersion: {version}\nRequires-Python: >=3.11\n\n",
        )
        archive.writestr(f"{info}/RECORD", "")
        archive.writestr(
            f"{info}/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        for name, raw in (
            members or {"learner/__init__.py": b"raise RuntimeError('never import')"}
        ).items():
            archive.writestr(name, raw)
    return path


def test_observe_members_without_importing_or_guessing_distribution_name(tmp_path):
    path = wheel(
        tmp_path,
        package="distribution",
        members={
            "learner/__init__.py": b"raise RuntimeError('never import')",
            "learner/models/forest.py": b"",
            "distribution-1.2.dist-info/top_level.txt": b"forged\n",
        },
    )
    (evidence,) = capture_dependency_wheels(tmp_path, ("distribution==1.2",))
    assert evidence.modules == ("learner", "learner.models", "learner.models.forest")
    assert evidence.digest == Digest.of_bytes(path.read_bytes())
    assert evidence.pin == "distribution==1.2"


@pytest.mark.parametrize(
    "fault", ["missing", "wrong-version", "ambiguous", "customize", "symlink"]
)
def test_missing_ambiguous_or_unsafe_wheel_refuses(tmp_path, fault):
    path = wheel(tmp_path)
    if fault == "missing":
        path.unlink()
    elif fault == "wrong-version":
        path.unlink()
        wheel(tmp_path, version="2.0")
    elif fault == "ambiguous":
        (tmp_path / "learner-1.2-1-py3-none-any.whl").write_bytes(path.read_bytes())
    elif fault == "customize":
        wheel(tmp_path, members={"unsafe.pth": b"import os"})
    else:
        target = tmp_path / "bytes"
        path.rename(target)
        path.symlink_to(target)
    with pytest.raises((ValueError, OSError)):
        capture_dependency_wheels(tmp_path, ("learner==1.2",))


def test_import_provider_collision_is_not_order_dependent(tmp_path):
    wheel(tmp_path)
    wheel(tmp_path, package="other")
    with pytest.raises(ValueError, match="collision"):
        capture_dependency_wheels(tmp_path, ("other==1.2", "learner==1.2"))


def test_relocated_and_native_members_do_not_admit_scripts_or_invalid_names(tmp_path):
    wheel(
        tmp_path,
        members={
            "learner-1.2.data/purelib/learner/core.py": b"",
            "learner-1.2.data/platlib/learner/native.cpython-311.so": b"",
            "learner-1.2.data/scripts/forbidden.py": b"",
            "invalid-name/forbidden.py": b"",
            "__init__.py": b"",
            "learner/data.csv": b"",
        },
    )
    (evidence,) = capture_dependency_wheels(tmp_path, ("learner==1.2",))
    assert evidence.modules == ("learner", "learner.core", "learner.native")


def test_bounded_inventory_refuses_an_excessive_directory(tmp_path):
    wheel(tmp_path)
    for number in range(1024):
        (tmp_path / str(number)).touch()
    with pytest.raises(ValueError, match="wheelhouse_limit"):
        capture_dependency_wheels(tmp_path, ("learner==1.2",))


def test_empty_or_conflicting_provider_claims_are_not_accepted(tmp_path):
    path = wheel(tmp_path)
    (evidence,) = capture_dependency_wheels(tmp_path, ("learner==1.2",))
    with pytest.raises(ValueError, match="unambiguous"):
        RepositoryReadinessPolicy(dependency_wheels=(evidence, evidence))
    path.unlink()
    wheel(tmp_path, members={"learner-1.2.dist-info/top_level.txt": b"learner\n"})
    with pytest.raises(ValueError):
        capture_dependency_wheels(tmp_path, ("learner==1.2",))


def artifacts(
    tmp_path,
    *,
    source=b"import learner\ndef predict(x:int)->int: return learner.score(x)\n",
    extras=None,
):
    wheel(tmp_path)
    providers = capture_dependency_wheels(tmp_path, ("learner==1.2",))
    files = {"model.py": source, **(extras or {})}
    catalog = scan_sources(files.items())
    graph = build_graph(catalog, files)
    readiness = assess_repository(
        catalog,
        graph,
        policy=RepositoryReadinessPolicy(
            execution={"modes": ("direct",)},
            dependency_wheels=providers,
        ),
    )
    policy = ExposurePolicy.model_validate(
        {
            "selection": {"include": ["python:model:predict"]},
            "interfaces": ["rest"],
            "execution": {"allowed": ["direct"]},
            "eligibility": {"allow_conditional": True},
        }
    )
    return catalog, graph, readiness, policy, files


def test_exact_wheel_evidence_preserves_conditional_state_and_pin_binding(tmp_path):
    catalog, graph, readiness, policy, files = artifacts(tmp_path)
    before = report_bytes(readiness)
    plan = plan_exposure(catalog, graph, readiness, policy=policy)
    assert plan.capabilities[0].repository_readiness.value == "conditional"
    assert before == report_bytes(readiness)
    assert json.loads(before)["policy"]["dependency_wheels"][0]["pin"] == "learner==1.2"
    with pytest.raises(BundleRefused, match="matching direct-service pins"):
        plan_repository_interface(
            catalog,
            graph,
            readiness,
            policy,
            plan,
            files,
            interface="rest",
            dependency_archives={
                p.name: p.read_bytes() for p in tmp_path.glob("*.whl")
            },
        )
    strict = ExposurePolicy.model_validate(
        {**policy.model_dump(), "eligibility": {"allow_conditional": False}}
    )
    with pytest.raises(ExposureRefused):
        plan_exposure(catalog, graph, readiness, policy=strict)


@pytest.mark.parametrize(
    "source,extras",
    [
        (b"import learner.missing\ndef predict(x:int)->int:return x\n", {}),
        (b"import unknown\ndef predict(x:int)->int:return x\n", {}),
        (
            b"from helper import missing\ndef predict(x:int)->int:return missing(x)\n",
            {"helper.py": b"def other():pass\n"},
        ),
        (
            b"from helper import *\ndef predict(x:int)->int:return x\n",
            {"helper.py": b"def other():pass\n"},
        ),
        (
            b"import learner\ndef predict(x:int)->int:return x\n",
            {"learner.py": b"raise RuntimeError('shadow')\n"},
        ),
    ],
)
def test_wheels_do_not_hide_required_dependency_defects(tmp_path, source, extras):
    catalog, graph, readiness, policy, _ = artifacts(
        tmp_path, source=source, extras=extras
    )
    with pytest.raises(ExposureRefused):
        plan_exposure(catalog, graph, readiness, policy=policy)


@pytest.mark.parametrize("fault", ["missing", "changed", "extra", "claimed-modules"])
def test_render_revalidates_provider_evidence_from_exact_retained_wheels(
    tmp_path, fault
):
    catalog, graph, readiness, policy, files = artifacts(tmp_path)
    archives = {p.name: p.read_bytes() for p in tmp_path.glob("*.whl")}
    application = ApplicationInputs(
        repository_digest=catalog.repository_digest, dependencies=("learner==1.2",)
    )
    plan = plan_exposure(catalog, graph, readiness, policy=policy)
    assert plan_repository_interface(
        catalog,
        graph,
        readiness,
        policy,
        plan,
        files,
        interface="rest",
        application=application,
        dependency_archives=archives,
    ).capabilities
    if fault == "missing":
        archives = {}
    elif fault == "extra":
        archives["extra.whl"] = b"invalid"
    elif fault == "changed":
        path = wheel(tmp_path, members={"learner/__init__.py": b"changed"})
        archives[path.name] = path.read_bytes()
    else:
        data = readiness.policy.model_dump()
        data["dependency_wheels"][0]["modules"] += ("forged",)
        readiness = assess_repository(
            catalog, graph, policy=RepositoryReadinessPolicy.model_validate(data)
        )
        plan = plan_exposure(catalog, graph, readiness, policy=policy)
    with pytest.raises(ValueError):
        plan_repository_interface(
            catalog,
            graph,
            readiness,
            policy,
            plan,
            files,
            interface="rest",
            application=application,
            dependency_archives=archives,
        )

"""Public source entrypoints fail closed before filesystem traversal or remote effects."""

import json
import os

import pytest
from analysis_authorization import analysis_policy

from apizr.analysis_contracts import GitAnalysisTarget, LocalTarget, PinnedRoot
from apizr.cli import main
from apizr.compiler import assess_readiness, prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy
from apizr.graph import analyze_repository, graph_repository
from apizr.operator_policy import AuthorizationDenied, OperatorPolicy, decide_analysis
from apizr.repository import ScanPolicy, scan, scan_sources
from apizr.repository.discovery import discover
from apizr.repository_readiness import RepositoryReadinessPolicy

EXPOSURE = ExposurePolicy.model_validate(
    {
        "interfaces": ["rest", "mcp"],
        "execution": {"allowed": ["direct"]},
        "selection": {"include": ["python:api:quote"]},
    }
)
READINESS = RepositoryReadinessPolicy.model_validate(
    {"execution": {"modes": ["direct"]}}
)


def call(name, root, authority):
    options = {"operator_policy": authority}
    if name == "discover":
        return discover(root, ScanPolicy(), **options)
    if name == "prepare":
        return prepare_exposure(
            root, policy=EXPOSURE, readiness_policy=READINESS, **options
        )
    return {
        "scan": scan,
        "analyze": analyze_repository,
        "graph": graph_repository,
        "readiness": assess_readiness,
    }[name](root, **options)


@pytest.mark.parametrize(
    "operation", ["discover", "scan", "analyze", "graph", "readiness", "prepare"]
)
@pytest.mark.parametrize(
    "kind,code",
    [
        ("missing", "operator_policy_required"),
        ("invalid", "operator_policy_invalid"),
        ("neighbor", "operator_analysis_denied"),
        ("empty", "operator_permissions_denied"),
        ("fetch", "operator_operation_denied"),
    ],
)
def test_all_public_filesystem_apis_refuse_before_traversal(
    tmp_path, monkeypatch, operation, kind, code
):
    authority = analysis_policy(tmp_path)
    if kind == "missing":
        authority = None
    elif kind == "invalid":
        authority = authority.model_copy(update={"grants": ("invalid",)})
    elif kind == "neighbor":
        authority = analysis_policy(tmp_path.parent / (tmp_path.name + "-neighbor"))
    elif kind == "empty":
        authority = authority.model_copy(
            update={
                "grants": (authority.grants[0].model_copy(update={"permissions": ()}),)
            }
        )
    elif kind == "fetch":
        authority = OperatorPolicy.model_validate_json(
            json.dumps(
                {
                    "schema": "apizr.operator-policy/v1",
                    "grants": [
                        {
                            "adapter": "git",
                            "operation": "fetch",
                            "permissions": ["git.fetch"],
                            "target": {
                                "transport": "https",
                                "repository": "https://example.org/repo.git",
                                "reference": "main",
                                "subdir": ".",
                            },
                        }
                    ],
                }
            )
        )

    def forbidden(*args, **kwargs):
        raise AssertionError("source access before admission")

    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr(os, "scandir", forbidden)
    with pytest.raises(AuthorizationDenied, match=code):
        call(operation, tmp_path, authority)


def test_pure_typed_decision_and_exact_scope(tmp_path, monkeypatch):
    authority = analysis_policy(tmp_path)

    def forbidden(*a, **k):
        pytest.fail("decision performed I/O")

    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr(os, "stat", forbidden)
    assert decide_analysis(authority, LocalTarget(root=str(tmp_path))).allowed
    assert not decide_analysis(
        authority, LocalTarget(root=str(tmp_path / "child"))
    ).allowed
    assert not decide_analysis(
        authority, LocalTarget.model_construct(root="relative")
    ).allowed
    assert not decide_analysis(
        authority,
        GitAnalysisTarget(repository="https://example.org/repo", reference="main"),
    ).allowed


def test_local_anchor_replacement_and_links(tmp_path, monkeypatch):
    root, outside = tmp_path / "project", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "api.py").write_text(
        "def quote(unit_price: float, quantity: int) -> float: return unit_price * quantity\n"
    )
    (outside / "secret.py").write_text("def secret(): return 'secret'\n")
    (root / "link.py").symlink_to(outside / "secret.py")
    authority = analysis_policy(root)
    identity = root.stat()
    pin = PinnedRoot(root=str(root), device=identity.st_dev, inode=identity.st_ino)
    result = scan(pin, operator_policy=authority)
    assert [c.id for c in result.capabilities] == ["python:api:quote"]
    root.rename(tmp_path / "old")
    root.mkdir()
    with pytest.raises(AuthorizationDenied, match="operator_source_changed"):
        scan(pin, operator_policy=authority)
    root.rmdir()
    root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(AuthorizationDenied, match="operator_source_unavailable"):
        scan(root, operator_policy=authority)
    # An ancestor link is also forbidden, even if the leaf itself is a directory.
    (outside / "nested").mkdir()
    with pytest.raises(AuthorizationDenied, match="operator_source_unavailable"):
        scan(root / "nested", operator_policy=analysis_policy(root / "nested"))


def test_open_descriptor_survives_path_replacement_and_rendering_never_rereads(
    tmp_path, monkeypatch
):
    import apizr.repository.discovery as discovery

    root = tmp_path / "project"
    root.mkdir()
    raw = b"def quote(unit_price: float, quantity: int) -> float: return unit_price * quantity\n"
    (root / "api.py").write_bytes(raw)
    original = discovery.open_analysis_root

    def anchor(*args, **kwargs):
        descriptor = original(*args, **kwargs)
        root.rename(tmp_path / "old")
        root.mkdir()
        (root / "api.py").write_text("def injected(): pass\n")
        return descriptor

    monkeypatch.setattr(discovery, "open_analysis_root", anchor)
    prepared = call("prepare", root, analysis_policy(root))
    assert prepared.evidence.sources["api.py"] == raw
    monkeypatch.setattr(
        discovery, "read_source", lambda *a, **k: pytest.fail("render reread")
    )
    for interface in ("rest", "mcp"):
        assert render_bundle(prepared, interface=interface)["source/api.py"] == raw


@pytest.mark.parametrize(
    "command",
    [
        ["scan"],
        ["graph"],
        ["readiness"],
        ["expose", "plan"],
        ["expose", "build", "rest"],
        ["expose", "build", "mcp"],
    ],
)
def test_cli_requires_authority_and_refusals_remain_off_stdout(
    tmp_path, monkeypatch, capfd, command
):
    # Config/policy validation may precede source admission, but no source read may.
    monkeypatch.setattr(os, "scandir", lambda *a: pytest.fail("source enumeration"))
    flags = (
        ["--policy", str(tmp_path / "exposure.json")] if command[0] == "expose" else []
    )
    (tmp_path / "exposure.json").write_text(EXPOSURE.model_dump_json())
    if "build" in command:
        flags += ["--output-dir", str(tmp_path / "bundle")]
    assert main([*command, str(tmp_path), *flags]) == 2
    output = capfd.readouterr()
    assert not output.out
    assert json.loads(output.err)["code"] == "operator_policy_required"


def test_memory_primitives_are_not_filesystem_authority():
    assert scan_sources([("api.py", b"def f(): pass")]).capabilities


def test_project_cannot_declare_authority(tmp_path):
    from apizr.workspace.project import load_project

    path = tmp_path / "apizr.toml"
    path.write_text(
        'schema_version="apizr.project/v1"\nroot="."\noperator_policy="operator.json"\n'
    )
    with pytest.raises(ValueError):
        load_project(path)


def test_pinned_root_is_a_restriction_not_an_authorization_bypass(tmp_path):
    identity = tmp_path.stat()
    source = PinnedRoot(
        root=str(tmp_path), device=identity.st_dev, inode=identity.st_ino
    )
    with pytest.raises(AuthorizationDenied, match="operator_policy_required"):
        scan(source)
    with pytest.raises(AuthorizationDenied, match="operator_source_invalid"):
        scan(
            source.model_copy(update={"root": "relative"}),
            operator_policy=analysis_policy(tmp_path),
        )

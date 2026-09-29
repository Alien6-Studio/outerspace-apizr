"""Explicit application inputs are static, bounded and retained with bundle evidence."""

import builtins
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

import pytest
from analysis_authorization import analysis_policy, authorized_main
from pydantic import ValidationError

from apizr.application import ApplicationConfig, ApplicationInputs, ApplicationResource
from apizr.application_resources import capture_resources
from apizr.capabilities.model import Digest
from apizr.compiler import prepare_exposure, render_bundle
from apizr.execution.policy import ExecutionPolicy
from apizr.exposure import ExposurePolicy
from apizr.operator_policy import AuthorizationDenied
from apizr.project import load_project
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_interfaces.runtime import load_bundle, validate_bundle
from apizr.repository_readiness import RepositoryReadinessPolicy

EXAMPLE = Path(__file__).parents[1] / "examples/application-inputs"


@pytest.fixture
def application_project(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(EXAMPLE, root)
    (root / "unrelated.json").write_text('"must not be packaged"')
    (root / ".env").write_text("must not be packaged")
    return root


def prepare(root, **kwargs):
    config = load_project(root / "apizr.toml")
    return prepare_exposure(
        config.root,
        operator_policy=analysis_policy(config.root),
        scan_policy=config.scan,
        policy=ExposurePolicy.model_validate_json(config.exposure_policy.read_bytes()),
        readiness_policy=RepositoryReadinessPolicy.model_validate_json(
            config.readiness_policy.read_bytes()
        ),
        application=kwargs.pop("application", config.application),
        **kwargs,
    )


def test_normalization_and_project_contract(tmp_path):
    path = tmp_path / "apizr.toml"
    path.write_text(
        'schema_version="apizr.project/v1"\n[application]\ndependencies=["Z_Name==1.2", "six==1.17.0"]\nresources=["data//z.txt", "./a.txt"]\n'
    )
    config = load_project(path)
    assert config.application.dependencies == ("six==1.17.0", "z-name==1.2")
    assert config.application.resources == ("a.txt", "data/z.txt")
    path.write_text('schema_version="apizr.project/v1"\n')
    assert load_project(path).application == ApplicationConfig()


@pytest.mark.parametrize(
    "pins",
    [
        ["six"],
        ["six-==1.0"],
        ["six.==1.0"],
        ["six>=1"],
        ["six==1.*"],
        ["six[extra]==1.0"],
        ["six==1.0;python_version>'3'"],
        ["six @ https://example.com/a.whl"],
        ["-r file"],
        ["six==1.0\nother==2.0"],
        ["Some_Name==1.0", "some-name==2.0"],
        ["six==1.0", "six==1.0"],
        ["six==1.0 "],
    ],
)
def test_dependency_refusals(pins):
    with pytest.raises(ValidationError):
        ApplicationConfig(dependencies=tuple(pins))


@pytest.mark.parametrize(
    "paths",
    [
        ["../file"],
        ["data/../file"],
        ["/etc/passwd"],
        ["C:/file"],
        ["data\\file"],
        [".env"],
        [".git/config"],
        ["data/.key"],
        ["data/file\x00"],
        ["data/file\n"],
        ["a/b", "a//b"],
        ["x", "./x"],
        ["."],
        [""],
    ],
)
def test_resource_path_refusals(paths):
    with pytest.raises(ValidationError):
        ApplicationConfig(resources=tuple(paths))


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "directory",
        "symlink",
        "parent_link",
        "fifo",
        "alias",
        "large",
        "total",
    ],
)
def test_resource_files_refuse_unsafe_inputs(tmp_path, monkeypatch, fault):
    root = tmp_path / "project"
    root.mkdir()
    resource = root / "resource"
    resource.write_bytes(b"data")
    paths = ["resource"]
    if fault == "missing":
        resource.unlink()
    elif fault == "directory":
        resource.unlink()
        resource.mkdir()
    elif fault == "symlink":
        resource.unlink()
        resource.symlink_to(tmp_path / "outside")
    elif fault == "parent_link":
        (root / "link").symlink_to(tmp_path, target_is_directory=True)
        (tmp_path / "outside").write_bytes(b"outside")
        paths = ["link/outside"]
    elif fault == "fifo":
        resource.unlink()
        os.mkfifo(resource)
    elif fault == "alias":
        os.link(resource, root / "alias")
        paths.append("alias")
    elif fault == "large":
        monkeypatch.setattr("apizr.application_resources.MAX_RESOURCE_BYTES", 3)
    else:
        (root / "second").write_bytes(b"data")
        paths.append("second")
        monkeypatch.setattr("apizr.application_resources.MAX_APPLICATION_BYTES", 5)
    with pytest.raises((ValueError, OSError)):
        capture_resources(
            root, ApplicationConfig(resources=tuple(paths)), analysis_policy(root)
        )


def test_resources_require_analysis_authorization_before_open(tmp_path, monkeypatch):
    config = ApplicationConfig(resources=("missing",))
    monkeypatch.setattr(
        os, "open", lambda *a, **kw: pytest.fail("read before authorization")
    )
    with pytest.raises(AuthorizationDenied):
        capture_resources(tmp_path, config, None)


def test_static_preparation_never_imports_installs_or_downloads(
    application_project, monkeypatch
):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name in {"formatter", "six"}:
            pytest.fail("application import during analysis")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *a, **kw: pytest.fail("package manager during analysis"),
    )
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **kw: pytest.fail("download during analysis"),
    )
    prepared = prepare(application_project)
    assert prepared.application.dependencies == ("six==1.17.0",)
    assert tuple(prepared.resources) == ("data/message.txt",)
    for interface in ("rest", "mcp"):
        files = render_bundle(prepared, interface=interface)
        assert "source/.env" not in files and "source/unrelated.json" not in files


@pytest.mark.parametrize("interface", ["rest", "mcp"])
def test_bundle_binding_retention_and_portability(
    application_project, tmp_path, interface
):
    prepared = prepare(application_project)
    files = render_bundle(prepared, interface=interface)
    contract = json.loads(files["repository-interface.json"])
    application = contract["application"]
    assert application["repository_digest"] == contract["repository_digest"]
    assert application["resources"] == [
        {
            "path": "data/message.txt",
            "digest": Digest.of_bytes(b"Portable caf\xc3\xa9\n").model_dump(),
            "size": 15,
        }
    ]
    assert files["application-requirements.txt"] == b"six==1.17.0\n"
    assert contract["sources"][0]["bundle_path"] == "source/src/formatter.py"
    (application_project / "unrelated.json").write_text("changed unrelated bytes")
    assert render_bundle(prepare(application_project), interface=interface) == files
    shutil.rmtree(application_project)
    assert render_bundle(prepared, interface=interface) == files
    bundle = tmp_path / "bundle"
    write_bundle(bundle, files)
    manifest, _ = validate_bundle(bundle, interface)
    assert manifest["application"] == application
    # Unit runtime uses the test environment's real six; installed minimal-core
    # absence and independent images are additionally proven by the OCI fixture.
    _, bindings, loader, _ = load_bundle(bundle, interface)
    try:
        assert bindings["python:formatter:message"]() == "PORTABLE CAFÉ"
    finally:
        loader.close()
    (bundle / "source/data/message.txt").write_text("tampered")
    with pytest.raises(ValueError):
        validate_bundle(bundle, interface)


def test_resource_and_dependency_changes_change_bundle_identity(application_project):
    first = render_bundle(prepare(application_project), interface="rest")
    config = ApplicationConfig(
        dependencies=("six==1.16.0",), resources=("data/message.txt",)
    )
    second = render_bundle(
        prepare(application_project, application=config), interface="rest"
    )
    (application_project / "data/message.txt").write_text("other resource")
    third = render_bundle(prepare(application_project), interface="rest")
    assert (
        len(
            {
                first["repository-interface.json"],
                second["repository-interface.json"],
                third["repository-interface.json"],
            }
        )
        == 3
    )


def test_empty_declarations_preserve_bundle_contract(application_project):
    prepared = prepare(application_project, application=ApplicationConfig())
    files = render_bundle(prepared, interface="rest")
    assert "application" not in json.loads(files["repository-interface.json"])
    assert "application-requirements.txt" not in files
    assert "source/data/message.txt" not in files


def test_cli_uses_explicit_project_application(application_project, tmp_path):
    output = tmp_path / "output"
    assert (
        authorized_main(
            [
                "expose",
                "build",
                "rest",
                "--project",
                str(application_project / "apizr.toml"),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    assert (output / "application-requirements.txt").read_bytes() == b"six==1.17.0\n"


def test_render_refuses_changed_resource_bytes_and_governed_application(
    application_project,
):
    from dataclasses import replace

    prepared = prepare(application_project)
    with pytest.raises(ValueError, match="resource content"):
        render_bundle(
            replace(prepared, resources={"data/message.txt": b"wrong"}),
            interface="rest",
        )
    with pytest.raises(ValueError, match="resource set"):
        render_bundle(replace(prepared, resources={}), interface="rest")
    with pytest.raises(ValueError, match="direct service"):
        render_bundle(prepared, interface="rest", execution_policy=ExecutionPolicy())


def test_application_identity_validation():
    digest = Digest.of_bytes(b"x")
    resource = ApplicationResource(path="x", digest=digest, size=1)
    with pytest.raises(ValidationError, match="ordered unique"):
        ApplicationInputs(repository_digest=digest, resources=(resource, resource))

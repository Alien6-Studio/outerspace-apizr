"""Actual CLI bridge binds retained wheel members to observed Run versions."""

import json
import zipfile

import pytest

from apizr.cli.commands.experiment import main
from apizr.experiments.store import DEFAULT_STORE, publish
from apizr.repository_readiness import RepositoryReadinessPolicy
from apizr.workspace.application_dependencies import capture_dependency_wheels

from .exposure_support import authority, project, record_for


@pytest.fixture
def external_command(tmp_path):
    source = project(tmp_path / "project")
    source.write_text("import scientific_sdk\n" + source.read_text())
    record = record_for(source)
    publish(source.parent / DEFAULT_STORE, record.plan, record.run)
    operator = tmp_path / "operator.json"
    operator.write_text(authority(source.parent).model_dump_json(by_alias=True))
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    path = wheels / "example_package-1.2.3-py3-none-any.whl"
    info = "example_package-1.2.3.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{info}/METADATA",
            "Metadata-Version: 2.3\nName: example-package\nVersion: 1.2.3\n\n",
        )
        archive.writestr(f"{info}/WHEEL", "Wheel-Version: 1.0\nTag: py3-none-any\n")
        archive.writestr(f"{info}/RECORD", "")
        archive.writestr(
            "scientific_sdk/__init__.py", "raise RuntimeError('must not import')\n"
        )
    output = tmp_path / "bundle"
    arguments = [
        "expose",
        record.run_digest,
        "--root",
        str(source.parent),
        "--operator-policy",
        str(operator),
        "--capability",
        "python:serving:predict",
        "--interface",
        "rest",
        "--artifact",
        "model",
        "--dependency",
        "example-package",
        "--dependency-wheelhouse",
        str(wheels),
        "--allow-conditional",
        "--output-dir",
        str(output),
    ]
    return arguments, wheels, output


def test_actual_cli_captures_wheels_without_importing_them(external_command, capfd):
    args, wheels, output = external_command
    assert main([*args, "--format", "json"]) == 0
    assert json.loads(capfd.readouterr().out)["binding"]["dependencies"] == [
        "example-package==1.2.3"
    ]
    report = json.loads((output / "repository-readiness.json").read_text())
    assert report["policy"]["dependency_wheels"][0]["modules"] == ["scientific_sdk"]
    assert (
        report["policy"]["dependency_wheels"][0]["filename"]
        == next(wheels.glob("*.whl")).name
    )


@pytest.mark.parametrize(
    "fault", ["missing", "wrong-pin", "invalid", "no-conditional", "declared-evidence"]
)
def test_bridge_cannot_substitute_claims_for_wheel_bytes(
    external_command, capfd, fault
):
    args, wheels, output = external_command
    path = next(wheels.glob("*.whl"))
    expected = 2
    if fault == "missing":
        path.unlink()
    elif fault == "wrong-pin":
        path.rename(wheels / path.name.replace("1.2.3", "1.2.4"))
    elif fault == "invalid":
        path.write_bytes(b"invalid ZIP")
    elif fault == "no-conditional":
        args.remove("--allow-conditional")
        expected = 1
    else:
        policy = output.parent / "policy.json"
        policy.write_text(
            RepositoryReadinessPolicy(
                dependency_wheels=capture_dependency_wheels(
                    wheels, ("example-package==1.2.3",)
                )
            ).model_dump_json()
        )
        args += ["--readiness-policy", str(policy)]
    assert main(args) == expected
    assert not output.exists()
    assert capfd.readouterr().err

"""Real static compiler, authorization, retained evidence and publication tests."""

import json
import shutil
from pathlib import Path

import pytest
from analysis_authorization import analysis_policy

from apizr.ci import CIError, CIResult, execute
from apizr.ci.runner import analysis_authority
from apizr.cli.commands.ci import main
from apizr.compiler import prepare_exposure, render_bundle
from apizr.config_files import absolute_path
from apizr.exposure import ExposurePolicy, plan_bytes
from apizr.onboarding.diagnostics import doctor
from apizr.operator_policy import decide_analysis
from apizr.project import load_project
from apizr.repository_readiness import RepositoryReadinessPolicy, report_bytes


def project(root: Path) -> Path:
    root.mkdir()
    (root / "src").mkdir()
    (root / "src/sample.py").write_text(
        "def add(a: int, b: int = 1) -> int: return a + b\n"
    )
    (root / "apizr.toml").write_text(
        'schema_version = "apizr.project/v1"\n'
        'exposure_policy = "exposure.json"\n'
        'readiness_policy = "readiness-policy.json"\n'
        '[scan]\nsource_roots = ["src"]\n'
    )
    (root / "readiness-policy.json").write_text('{"execution":{"modes":["direct"]}}')
    (root / "exposure.json").write_text(
        json.dumps(
            {
                "selection": {"include": ["python:sample:add"]},
                "interfaces": ["rest", "mcp"],
                "execution": {"allowed": ["direct"]},
            }
        )
    )
    return root / "apizr.toml"


@pytest.mark.parametrize("operation", ["check", "build-rest", "build-mcp"])
def test_real_compiler_parity_determinism_and_portability(
    tmp_path, monkeypatch, operation
):
    config_path = project(tmp_path / "project")
    monkeypatch.setenv("GITHUB_TOKEN", "SECRET_GITHUB_TOKEN_SENTINEL")
    monkeypatch.setenv("CI_JOB_TOKEN", "SECRET_JOB_TOKEN_SENTINEL")
    for name in ("first", "second"):
        result = execute(
            operation,
            project=config_path,
            output_dir=tmp_path / name,
            authorize_project_analysis=True,
        )
        assert result.exit_code == 0
        raw = (tmp_path / name / "result.json").read_bytes()
        assert CIResult.model_validate_json(raw, strict=True) == result
        combined = b"".join(
            p.read_bytes() for p in (tmp_path / name).rglob("*") if p.is_file()
        )
        for forbidden in (str(tmp_path).encode(), b"SECRET_GITHUB", b"SECRET_JOB"):
            assert forbidden not in combined

    def files(root):
        return {
            str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        }

    assert files(tmp_path / "first") == files(tmp_path / "second")
    config = load_project(config_path)
    prepared = prepare_exposure(
        config.root,
        operator_policy=analysis_policy(config.root),
        policy=ExposurePolicy.model_validate_json(config.exposure_policy.read_bytes()),
        scan_policy=config.scan,
        graph_policy=config.graph,
        application=config.application,
        readiness_policy=RepositoryReadinessPolicy.model_validate_json(
            config.readiness_policy.read_bytes()
        ),
    )
    assert (tmp_path / "first/readiness.json").read_bytes() == report_bytes(
        prepared.readiness
    )
    assert (tmp_path / "first/exposure-plan.json").read_bytes() == plan_bytes(
        prepared.plan
    )
    if operation != "check":
        assert files(tmp_path / "first/bundle") == render_bundle(
            prepared, interface=operation[6:]
        )
    relocated = tmp_path / "relocated"
    shutil.copytree(config_path.parent, relocated)
    execute(
        operation,
        project=relocated / "apizr.toml",
        output_dir=tmp_path / "third",
        authorize_project_analysis=True,
    )
    assert files(tmp_path / "first") == files(tmp_path / "third")


def test_exact_ephemeral_authority_and_policy_parity(tmp_path):
    config = project(tmp_path / "project")
    root = absolute_path(config.parent)
    policy = analysis_authority(root)
    assert len(policy.grants) == 1
    grant = policy.grants[0]
    assert grant.permissions == ("source.analyze",)
    assert grant.adapter == "repository" and grant.operation == "analyze"
    assert grant.target.root == str(root)
    assert decide_analysis(policy, grant.target).allowed
    assert not decide_analysis(
        policy, grant.target.model_copy(update={"root": str(root.parent)})
    ).allowed
    assert doctor(project=config, operator_policy=policy).exit_code == 0
    path = tmp_path / "operator.json"
    path.write_text(policy.model_dump_json(by_alias=True))
    a = execute(
        "check",
        project=config,
        output_dir=tmp_path / "a",
        authorize_project_analysis=True,
    )
    b = execute(
        "check", project=config, output_dir=tmp_path / "b", operator_policy=path
    )
    assert a == b
    assert not (config.parent / ".apizr/operator.json").exists()


@pytest.mark.parametrize(
    "args", [[], ["--operator-policy", "absent.json", "--authorize-project-analysis"]]
)
def test_authority_required_before_analysis(tmp_path, monkeypatch, capsys, args):
    config = project(tmp_path / "project")
    monkeypatch.setattr(
        "apizr.ci.runner.prepare_exposure",
        lambda *a, **kw: pytest.fail("analysis attempted"),
    )
    assert main(["check", "--project", str(config), *args]) == 2
    assert capsys.readouterr().err == "ci_arguments_invalid\n"


@pytest.mark.parametrize("kind", ["occupied", "symlink", "parent-symlink", "traversal"])
def test_output_conflict_never_overwrites_or_analyzes(tmp_path, monkeypatch, kind):
    config = project(tmp_path / "project")
    output = tmp_path / "output"
    if kind == "occupied":
        output.mkdir()
        (output / "secret").write_text("preserve")
    elif kind == "symlink":
        output.symlink_to(config.parent, target_is_directory=True)
    elif kind == "parent-symlink":
        output.symlink_to(config.parent, target_is_directory=True)
        output = output / "child"
    else:
        output = tmp_path / "missing/../output"
    monkeypatch.setattr(
        "apizr.ci.runner.prepare_exposure",
        lambda *a, **kw: pytest.fail("analysis attempted"),
    )
    with pytest.raises((CIError, OSError, ValueError)):
        execute(
            "check", project=config, output_dir=output, authorize_project_analysis=True
        )
    assert config.exists()
    if kind == "occupied":
        assert (output / "secret").read_text() == "preserve"


def test_refusal_retains_readiness_without_plan(tmp_path):
    config = project(tmp_path / "project")
    policy = json.loads((config.parent / "exposure.json").read_text())
    policy["selection"]["include"] = ["python:sample:missing"]
    (config.parent / "exposure.json").write_text(json.dumps(policy))
    output = tmp_path / "output"
    result = execute(
        "check", project=config, output_dir=output, authorize_project_analysis=True
    )
    assert result.exit_code == 1 and result.diagnostic == "ci_exposure_refused"
    assert (output / "readiness.json").exists()
    assert (output / "doctor.json").exists()
    assert not (output / "exposure-plan.json").exists()


def test_fixed_errors_cancel_and_bounded_outputs(tmp_path, monkeypatch, capsys):
    config = project(tmp_path / "project")
    assert main(["delivery", "--token", "SENSITIVE"]) == 2
    assert "SENSITIVE" not in capsys.readouterr().err
    monkeypatch.setattr("apizr.ci.runner.MAX_TOTAL_BYTES", 1)
    with pytest.raises(CIError, match="ci_artifact_limit"):
        execute(
            "check",
            project=config,
            output_dir=tmp_path / "output",
            authorize_project_analysis=True,
        )
    assert not (tmp_path / "output").exists()

    def cancel(*a, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr("apizr.cli.commands.ci.execute", cancel)
    assert main(["check", "--authorize-project-analysis"]) == 130
    assert capsys.readouterr().err == "ci_cancelled\n"


def test_readiness_of_unselected_code_still_refuses(tmp_path):
    config = project(tmp_path / "project")
    source = config.parent / "src/sample.py"
    source.write_text(source.read_text() + "\ndef unknown(): yield 1\n")
    result = execute(
        "check",
        project=config,
        output_dir=tmp_path / "out",
        authorize_project_analysis=True,
    )
    assert result.exit_code == 1 and result.diagnostic == "ci_readiness_refused"
    assert result.exposure_plan_digest is not None
    assert result.readiness_exit_code == 1


def test_interface_refusal_and_doctor_failure_are_distinct(tmp_path, capsys):
    config = project(tmp_path / "project")
    policy = config.parent / "exposure.json"
    data = json.loads(policy.read_text())
    data["interfaces"] = ["rest"]
    policy.write_text(json.dumps(data))
    args = ["--project", str(config), "--authorize-project-analysis"]
    assert main(["build-mcp", *args, "--output-dir", str(tmp_path / "mcp")]) == 1
    assert capsys.readouterr().out == "ci_bundle_refused\n"
    policy.write_text('{"SECRET_POLICY":true}')
    assert main(["check", *args, "--output-dir", str(tmp_path / "invalid")]) == 2
    assert capsys.readouterr().out == "ci_doctor_failed\n"
    assert b"SECRET_POLICY" not in (tmp_path / "invalid/doctor.json").read_bytes()


def test_cli_fixed_configuration_and_authority_errors(tmp_path, capsys):
    config = project(tmp_path / "project")
    policy = tmp_path / "operator.json"
    policy.write_text("secret malformed token $()")
    assert (
        main(
            [
                "check",
                "--project",
                str(config),
                "--operator-policy",
                str(policy),
                "--output-dir",
                str(tmp_path / "o"),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err == "ci_authorization_refused\n"
    assert (
        main(
            [
                "check",
                "--project",
                str(tmp_path / "SECRET"),
                "--authorize-project-analysis",
                "--output-dir",
                str(tmp_path / "o"),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err == "ci_configuration_invalid\n"
    assert not (tmp_path / "o").exists()
    with pytest.raises(CIError, match="arguments_invalid"):
        execute(
            "publish",
            project=config,
            output_dir=tmp_path / "o",
            authorize_project_analysis=True,
        )
    with pytest.raises(CIError, match="authority_required"):
        execute("check", project=config, output_dir=tmp_path / "o")


def test_project_is_not_imported_or_executed(tmp_path):
    config = project(tmp_path / "project")
    sentinel = tmp_path / "EXECUTED"
    source = config.parent / "src/sample.py"
    source.write_text(
        f"open({str(sentinel)!r}, 'w').write('executed')\n" + source.read_text()
    )
    result = execute(
        "check",
        project=config,
        output_dir=tmp_path / "out",
        authorize_project_analysis=True,
    )
    assert result.exit_code == 1
    assert not sentinel.exists()


def test_empty_output_success_single_analysis_and_atomic_cancellation(
    tmp_path, monkeypatch
):
    config = project(tmp_path / "project")
    original = prepare_exposure
    calls = []

    def once(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr("apizr.ci.runner.prepare_exposure", once)
    out = tmp_path / "empty"
    out.mkdir()
    execute(
        "build-rest", project=config, output_dir=out, authorize_project_analysis=True
    )
    assert calls == [1]

    def cancel(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("apizr.ci.runner.render_bundle", cancel)
    with pytest.raises(KeyboardInterrupt):
        execute(
            "build-rest",
            project=config,
            output_dir=tmp_path / "cancelled",
            authorize_project_analysis=True,
        )
    assert not (tmp_path / "cancelled").exists()
    assert not list(tmp_path.glob(".apizr-stage-*"))


def test_result_rejects_inconsistent_or_nonportable_evidence(tmp_path):
    from pydantic import ValidationError

    config = project(tmp_path / "project")
    result = execute(
        "check",
        project=config,
        output_dir=tmp_path / "out",
        authorize_project_analysis=True,
    )
    data = result.model_dump(mode="json")
    variants = [
        {"schema_version": "apizr.ci-result/v2"},
        {"secret": "not allowed"},
        {"artifacts": list(reversed(data["artifacts"]))},
        {"readiness_exit_code": None},
        {"bundle_interface": "rest"},
        {"bundle_interface": "mcp", "bundle_manifest_digest": data["project_digest"]},
        {"exposure_plan_digest": None},
    ]
    for patch in variants:
        with pytest.raises(ValidationError):
            CIResult.model_validate_json(json.dumps(dict(data, **patch)), strict=True)
    for path in ("/absolute", "../escape", "result.json", "C:\\secret"):
        modified = json.loads(json.dumps(data))
        modified["artifacts"][0]["path"] = path
        with pytest.raises(ValidationError):
            CIResult.model_validate_json(json.dumps(modified), strict=True)

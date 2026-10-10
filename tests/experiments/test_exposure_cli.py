"""Canonical Run loading, explicit selectors and atomic serving output."""

import json

import pytest

from apizr.cli.commands.experiment import main
from apizr.experiments.store import DEFAULT_STORE, publish

from .exposure_support import authority, project, record_for


@pytest.fixture
def command(tmp_path):
    path = project(tmp_path / "project")
    record = record_for(path)
    publish(path.parent / DEFAULT_STORE, record.plan, record.run)
    policy = tmp_path / "operator.json"
    policy.write_text(authority(path.parent).model_dump_json(by_alias=True))
    output = tmp_path / "bundle"
    return (
        [
            "expose",
            record.run_digest,
            "--root",
            str(path.parent),
            "--operator-policy",
            str(policy),
            "--capability",
            "python:serving:predict",
            "--interface",
            "rest",
            "--artifact",
            "model",
            "--output-dir",
            str(output),
        ],
        record,
        output,
    )


@pytest.mark.parametrize("format", ["json", "text"])
def test_command_uses_validated_store_and_reports_full_identity(command, capfd, format):
    args, record, output = command
    assert main([*args, "--format", format]) == 0
    result = capfd.readouterr()
    assert not result.err
    assert record.run_digest in result.out and record.plan_digest in result.out
    if format == "json":
        value = json.loads(result.out)
        assert value["binding"] == json.loads(
            (output / "experiment-exposure.json").read_bytes()
        )
        assert str(output) not in result.out
    else:
        assert "Resources: model" in result.out and "Interface: rest" in result.out


@pytest.mark.parametrize("argument", ["--capability", "--interface", "--output-dir"])
def test_selection_required(command, argument):
    args, _, output = command
    index = args.index(argument)
    del args[index : index + 2]
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2 and not output.exists()


@pytest.mark.parametrize(
    "extra",
    [
        ["--capability", "python:serving:train"],
        ["--interface", "mcp"],
        ["--artifact", "model"],
        ["--all-ready"],
    ],
)
def test_duplicate_or_implicit_selection_refused(command, extra):
    args, _, output = command
    if "--all-ready" in extra:
        with pytest.raises(SystemExit):
            main([*args, *extra])
    else:
        assert main([*args, *extra]) == 2
    assert not output.exists()


def test_store_corruption_refuses_before_output(command, capfd):
    args, record, output = command
    root = output.parent / "project"
    (root / DEFAULT_STORE / "runs" / (record.run_digest + ".json")).write_bytes(b"{}")
    assert main(args) == 2 and not output.exists()
    assert "store" in capfd.readouterr().err


def test_missing_authority_refused(command, capfd):
    args, _, output = command
    index = args.index("--operator-policy")
    del args[index : index + 2]
    assert main(args) == 2 and not output.exists()
    assert "operator_policy_required" in capfd.readouterr().err


def test_readiness_refusal_and_invalid_policy(command, capfd):
    args, _, output = command
    policy = output.parent / "readiness.json"
    policy.write_text('{"execution":{"modes":["local-process"]}}')
    assert main([*args, "--readiness-policy", str(policy)]) == 1
    assert "repository_exposure_refused" in capfd.readouterr().err
    assert not output.exists()
    policy.write_text("INVALID")
    assert main([*args, "--readiness-policy", str(policy)]) == 2
    assert not output.exists()


def test_bundle_refusal_and_publication_failure(command, monkeypatch, capfd):
    from apizr.repository_interfaces import BundleRefused

    def refuse(*args, **kwargs):
        raise BundleRefused("APIZR-BUNDLE-005: public name collision")

    args, _, output = command
    with monkeypatch.context() as patch:
        patch.setattr("apizr.experiments.exposure.render_bundle", refuse)
        assert main(args) == 1 and not output.exists()
        assert "APIZR-BUNDLE-005" in capfd.readouterr().err
    output.mkdir()
    (output / "sentinel").write_bytes(b"preserve")
    assert main(args) == 2
    assert list(output.iterdir()) == [output / "sentinel"]


def test_explicit_store_and_dependency_summary(command, capfd):
    args, _, output = command
    store = output.parent / "project" / DEFAULT_STORE
    assert main([*args, "--store", str(store), "--dependency", "example-package"]) == 0
    assert "Dependencies: example-package==1.2.3" in capfd.readouterr().out


def test_no_selected_outputs_summary(command, capfd):
    args, _, _ = command
    index = args.index("--artifact")
    del args[index : index + 2]
    assert main(args) == 0
    assert "Resources: none" in capfd.readouterr().out

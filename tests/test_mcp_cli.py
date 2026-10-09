import json
import os
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from analysis_authorization import analysis_policy

from apizr import cli, mcp_cli
from apizr.analysis_session import read_session
from apizr.extension_runtime import PrerequisiteMissing
from apizr.plugins.local import PluginError


@pytest.fixture
def launch(tmp_path):
    project = tmp_path / "apizr.toml"
    project.write_text('schema_version="apizr.project/v1"\nroot="."\n')
    authority = tmp_path / "operator.json"
    authority.write_text(analysis_policy(tmp_path).model_dump_json())
    return ["serve", "--project", str(project), "--operator-policy", str(authority)]


@pytest.mark.parametrize(
    "error",
    [
        PluginError("plugin_not_installed"),
        PluginError("plugin_inactive"),
        PluginError("activation_mismatch"),
        PrerequisiteMissing(),
        OSError(),
    ],
)
def test_mcp_launcher_refusal(monkeypatch, capsys, error, launch):
    def resolve(*a, **k):
        raise error

    monkeypatch.setattr(mcp_cli, "admitted_extension", resolve)
    assert mcp_cli.main(launch) == 2
    assert capsys.readouterr().out == ""


def test_mcp_launcher_exact_admitted_interpreter_and_empty_environment(
    monkeypatch, launch
):
    record = SimpleNamespace(python="/plugins/id/venv/bin/python", module="apizr_mcp")
    seen = []
    monkeypatch.setattr(
        mcp_cli,
        "admitted_extension",
        lambda name, **kw: seen.append((name, kw)) or nullcontext((record, 42)),
    )

    class Executed(Exception):
        pass

    def execute(path, args, env):
        assert path == record.python
        assert args[:6] == [record.python, "-I", "-B", "-m", "apizr_mcp", "serve"]
        assert env == {}
        assert "--timeout-ms" in args
        assert "--project" not in args and "--operator-policy" not in args
        descriptor = int(args[args.index("--session-fd") + 1])
        assert os.get_inheritable(descriptor)
        # Editing configuration after capture cannot change exec's authority.
        Path(launch[-1]).write_text("invalid now")
        Path(launch[2]).write_text("invalid now")
        scope = read_session(os.dup(descriptor))
        assert scope.operator_policy.grants[0].target.root == scope.root
        raise Executed

    monkeypatch.setattr(mcp_cli.os, "execve", execute)
    with pytest.raises(Executed):
        cli.main(["mcp", *launch, "--plugins-dir", "/plugins"])
    assert seen == [
        ("outerspace-apizr-mcp", {"directory": Path("/plugins"), "inherit": True})
    ]


def test_existing_mcp_installation_retains_its_lease(monkeypatch):
    events = []
    record = SimpleNamespace(module="apizr_mcp")

    @contextmanager
    def admit(name, **kwargs):
        events.append(name)
        assert kwargs == {"directory": Path("/plugins"), "inherit": True}
        if name == "outerspace-apizr-mcp":
            raise PluginError("plugin_not_installed")
        try:
            yield record, 42
        finally:
            events.append("released")

    monkeypatch.setattr(mcp_cli, "admitted_extension", admit)
    with mcp_cli._admitted_mcp(Path("/plugins")) as admitted:
        assert admitted == (record, 42)
        assert events == ["outerspace-apizr-mcp", "apizr-mcp"]
    assert events[-1] == "released"


@pytest.mark.parametrize(
    "error",
    [
        PluginError("plugin_inactive"),
        PluginError("activation_mismatch"),
        PluginError("invalid_inventory"),
        PrerequisiteMissing(),
    ],
)
def test_new_mcp_identity_refusal_does_not_select_an_old_identity(monkeypatch, error):
    names = []

    def admit(name, **kwargs):
        names.append(name)
        raise error

    monkeypatch.setattr(mcp_cli, "admitted_extension", admit)
    with pytest.raises(type(error)):
        with mcp_cli._admitted_mcp(Path("/plugins")):
            pytest.fail("invalid identity admitted")
    assert names == ["outerspace-apizr-mcp"]


def test_entrypoint_and_relative_root_refused(monkeypatch, capsys, launch):
    monkeypatch.setattr(
        mcp_cli,
        "admitted_extension",
        lambda *a, **k: nullcontext((SimpleNamespace(module="other"), 42)),
    )
    assert mcp_cli.main(["serve", "--project", "apizr.toml"]) == 2
    assert "absolute_project_required" in capsys.readouterr().err
    assert mcp_cli.main(launch) == 2
    assert "mcp_entrypoint_mismatch" in capsys.readouterr().err


def test_required_project_and_no_free_command():
    for arguments in (
        ["serve"],
        ["serve", "--project", "/apizr.toml", "--command", "sh"],
    ):
        with pytest.raises(SystemExit) as error:
            mcp_cli.main(arguments)
        assert error.value.code == 2


@pytest.mark.parametrize(
    "kind,code",
    [
        ("missing", "operator_policy_required"),
        ("invalid", "operator_policy_invalid"),
        ("neighbor", "operator_analysis_denied"),
    ],
)
def test_no_server_or_worker_on_source_refusal(
    launch, tmp_path, monkeypatch, capsys, kind, code
):
    def forbidden(*a, **k):
        pytest.fail("plugin admission or source traversal before authority")

    monkeypatch.setattr(mcp_cli, "admitted_extension", forbidden)
    monkeypatch.setattr(os, "scandir", forbidden)
    if kind == "missing":
        launch = launch[:-2]
    elif kind == "invalid":
        Path(launch[-1]).write_text("invalid")
    else:
        Path(launch[-1]).write_text(
            analysis_policy(tmp_path / "neighbor").model_dump_json()
        )
    assert mcp_cli.main(launch) == 2
    output = capsys.readouterr()
    assert not output.out and json.loads(output.err)["code"] == code

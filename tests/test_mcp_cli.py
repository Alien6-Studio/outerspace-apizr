from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from apizr import cli, mcp_cli
from apizr.extension_runtime import PrerequisiteMissing
from apizr.local_plugins import PluginError


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
def test_mcp_launcher_refusal(monkeypatch, capsys, error):
    def resolve(*a, **k):
        raise error

    monkeypatch.setattr(mcp_cli, "admitted_extension", resolve)
    assert mcp_cli.main(["serve", "--project", "/project/apizr.toml"]) == 2
    assert capsys.readouterr().out == ""


def test_mcp_launcher_exact_admitted_interpreter_and_empty_environment(monkeypatch):
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
        raise Executed

    monkeypatch.setattr(mcp_cli.os, "execve", execute)
    with pytest.raises(Executed):
        cli.main(
            [
                "mcp",
                "serve",
                "--project",
                "/project/apizr.toml",
                "--plugins-dir",
                "/plugins",
            ]
        )
    assert seen == [("apizr-mcp", {"directory": Path("/plugins"), "inherit": True})]


def test_entrypoint_and_relative_root_refused(monkeypatch, capsys):
    monkeypatch.setattr(
        mcp_cli,
        "admitted_extension",
        lambda *a, **k: nullcontext((SimpleNamespace(module="other"), 42)),
    )
    assert mcp_cli.main(["serve", "--project", "apizr.toml"]) == 2
    assert "absolute_project_required" in capsys.readouterr().err
    assert mcp_cli.main(["serve", "--project", "/apizr.toml"]) == 2
    assert "mcp_entrypoint_mismatch" in capsys.readouterr().err


def test_required_project_and_no_free_command():
    for arguments in (
        ["serve"],
        ["serve", "--project", "/apizr.toml", "--command", "sh"],
    ):
        with pytest.raises(SystemExit) as error:
            mcp_cli.main(arguments)
        assert error.value.code == 2

import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from analysis_authorization import analysis_policy
from apizr_mcp import launcher

from apizr import mcp_cli
from apizr.local_plugins import PluginError


@pytest.fixture
def arguments(tmp_path, monkeypatch):
    project = tmp_path / "apizr.toml"
    project.write_text('schema_version="apizr.project/v1"\nroot="."\n')
    policy = tmp_path / "operator.json"
    policy.write_text(analysis_policy(tmp_path).model_dump_json())
    monkeypatch.setattr(
        launcher.sys,
        "argv",
        [
            "outerspace-apizr-mcp",
            "--project",
            str(project),
            "--operator-policy",
            str(policy),
            "--plugins-dir",
            str(tmp_path / "plugins"),
        ],
    )


@pytest.mark.parametrize("code", ["plugin_not_installed", "plugin_inactive"])
def test_registry_launcher_preserves_admission(arguments, monkeypatch, capsys, code):
    def refuse(*args, **kwargs):
        raise PluginError(code)

    monkeypatch.setattr(mcp_cli, "admitted_extension", refuse)
    assert launcher.main() == 2
    output = capsys.readouterr()
    assert not output.out and code in output.err


def test_registry_launcher_executes_only_admitted_interpreter(arguments, monkeypatch):
    record = SimpleNamespace(python="/approved/venv/bin/python", module="apizr_mcp")
    monkeypatch.setattr(
        mcp_cli, "admitted_extension", lambda *a, **k: nullcontext((record, 42))
    )

    class Executed(Exception):
        pass

    def execute(path, args, env):
        assert path == record.python
        assert args[:6] == [path, "-I", "-B", "-m", "apizr_mcp", "serve"]
        assert env == {}
        assert "--session-fd" in args
        raise Executed

    monkeypatch.setattr(mcp_cli.os, "execve", execute)
    with pytest.raises(Executed):
        launcher.main()


def test_registry_identity_and_read_only_launch_contract():
    import tomllib

    root = Path(__file__).resolve().parents[2]
    descriptor = json.loads((root / "server.json").read_text())
    marker = f"<!-- mcp-name: {descriptor['name']} -->"
    assert marker in (root / "plugins/mcp/README.md").read_text()
    package = descriptor["packages"][0]
    project = tomllib.loads((root / "plugins/mcp/pyproject.toml").read_text())[
        "project"
    ]
    assert project["scripts"][package["identifier"]] == "apizr_mcp.launcher:main"
    assert package["version"] == descriptor["version"] == project["version"] == "0.4.4"
    assert package["transport"] == {"type": "stdio"}
    assert "remotes" not in descriptor
    assert {argument["name"] for argument in package["packageArguments"]} == {
        "--project",
        "--operator-policy",
        "--plugins-dir",
    }

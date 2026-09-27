"""Git admission is pure, exact and shared by every managed acquisition."""

import builtins
import copy
import io
import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

from apizr.cli import main
from apizr.git_source import AcquisitionLimits, acquire_snapshot
from apizr.git_source.contracts import GitTarget
from apizr.operator_policy import (
    AuthorizationDenied,
    OperatorPolicy,
    decide_git,
)

from .authorization import document, policy

pytestmark = pytest.mark.timeout(30)
COMMANDS = [
    ["readiness", "--report"],
    ["expose", "plan", "--interface", "rest", "--execution-mode", "direct"],
    [
        "expose",
        "build",
        "rest",
        "--interface",
        "rest",
        "--execution-mode",
        "direct",
        "--output-dir",
        "unused",
    ],
    [
        "expose",
        "build",
        "mcp",
        "--interface",
        "mcp",
        "--execution-mode",
        "direct",
        "--output-dir",
        "unused",
    ],
]
CASES = [
    "missing",
    "invalid",
    "build",
    "attest",
    "push",
    "publish",
    "repository",
    "neighbor",
    "encoded",
    "ref",
    "subdir",
    "prefix",
    "transport",
    "agent",
    "known",
    "user",
    "port",
    "ca",
    "permissions",
]


def inputs(transport):
    if transport == "ssh":
        return "ssh://git@git.example:2222/team/project.git", {
            "ssh_agent_socket": Path("/trust/agent"),
            "ssh_known_hosts": Path("/trust/known_hosts"),
        }
    return "https://git.example/team/project.git", {}


def scenario(transport, case):
    url, options = inputs(transport)
    raw = document(url, "refs/heads/main", subdir="src", **options)
    target = raw["grants"][0]["target"]
    code = "operator_git_source_denied"
    if case == "missing":
        code = "operator_policy_required"
    elif case == "invalid":
        raw["schema"] = "invalid"
        code = "operator_policy_invalid"
    elif case in {"build", "attest", "push", "publish"}:
        all_grants = json.loads(
            (
                Path(__file__).resolve().parents[2] / "docs/examples/operator.json"
            ).read_bytes()
        )
        raw["grants"] = [g for g in all_grants["grants"] if g["operation"] == case]
        assert raw["grants"]
        code = "operator_operation_denied"
    elif case == "permissions":
        raw["grants"][0]["permissions"] = []
        code = "operator_permissions_denied"
    elif case == "ref":
        target["reference"] = "main"
    elif case in {"subdir", "prefix"}:
        target["subdir"] = "src-neighbor" if case == "subdir" else "src/child"
    elif case == "transport":
        other, other_options = inputs("https" if transport == "ssh" else "ssh")
        raw = document(other, "refs/heads/main", subdir="src", **other_options)
    elif case in {"repository", "neighbor", "encoded"}:
        suffix = {
            "repository": "other.git",
            "neighbor": "project.git-other",
            "encoded": "%70roject.git",
        }[case]
        if transport == "ssh" and case == "encoded":
            # SCP relative and SSH absolute paths are not equivalent identities.
            target["repository"] = "git@git.example:team/project.git"
        else:
            target["repository"] = url.rsplit("/", 1)[0] + "/" + suffix
    elif case in {"agent", "known", "user", "port"}:
        if transport != "ssh":
            target["repository"] += "/" + case
        elif case in {"agent", "known"}:
            target["ssh_agent_socket" if case == "agent" else "ssh_known_hosts"] += (
                "-other"
            )
        else:
            target["repository"] = (
                url.replace("git@", "other@")
                if case == "user"
                else url.replace(":2222/", ":2223/")
            )
    elif case == "ca":
        if transport == "https":
            target["ca_file"] = "/trust/other-ca.pem"
        else:
            target["ssh_known_hosts"] = "/trust/other-ca.pem"
    return url, options, raw, code


def traps(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("effect before Git authorization")

    def guard(original):
        def checked(path, *args, **kwargs):
            assert not str(path).startswith("/trust/")
            return original(path, *args, **kwargs)

        return checked

    for owner, name in [
        (builtins, "open"),
        (io, "open"),
        (os, "open"),
        (os, "stat"),
        (os, "lstat"),
    ]:
        monkeypatch.setattr(owner, name, guard(getattr(owner, name)))
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr("apizr.git_source.acquisition.TemporaryDirectory", forbidden)
    monkeypatch.setattr("apizr.git_source.acquisition.shutil.which", forbidden)
    monkeypatch.setattr("apizr.git_source.acquisition.configure_ssh", forbidden)


@pytest.mark.parametrize("transport", ["https", "ssh"])
@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("command", COMMANDS)
def test_cli_and_api_refuse_before_effect(
    transport, case, command, tmp_path, monkeypatch, capsys
):
    url, options, raw, code = scenario(transport, case)
    path = tmp_path / "operator.json"
    path.write_text(json.dumps(raw))
    selected = (
        None
        if case == "missing"
        else OperatorPolicy.model_construct(schema_version="invalid", grants=())
        if case == "invalid"
        else OperatorPolicy.model_validate_json(json.dumps(raw))
    )
    # Untrusted settings are never a source of authority, even when valid.
    allowed = document(url, "refs/heads/main", subdir="src", **options)
    for name in ("catalog.json", "profile.json"):
        (tmp_path / name).write_text(json.dumps(allowed))
    (tmp_path / "apizr.toml").write_text('operator_policy = "operator.json"')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APIZR_OPERATOR_POLICY", str(path))
    traps(monkeypatch)
    with pytest.raises(AuthorizationDenied) as caught:
        with acquire_snapshot(
            url, "refs/heads/main", subdir="src", operator_policy=selected, **options
        ):
            pytest.fail("acquired without authorization")
    assert caught.value.code == code
    args = [*command, "--git", url, "--ref", "refs/heads/main", "--subdir", "src"]
    for name, value in options.items():
        args.extend(["--" + name.replace("_", "-"), str(value)])
    if case != "missing":
        args.extend(["--operator-policy", str(path)])
    assert main(args) == 2
    result = capsys.readouterr()
    assert result.out == "" and json.loads(
        result.err
    ) == caught.value.decision.model_dump(by_alias=True)
    assert not (tmp_path / "unused").exists()


@pytest.mark.parametrize("case", CASES + ["authorized"])
@pytest.mark.parametrize("transport", ["https", "ssh"])
def test_pure_exact_decision(transport, case, monkeypatch):
    url, options, raw, code = scenario(transport, case)
    if case == "authorized":
        code = "authorized"
    selected = (
        None
        if case == "missing"
        else OperatorPolicy.model_construct(schema_version="invalid", grants=())
        if case == "invalid"
        else OperatorPolicy.model_validate_json(json.dumps(raw))
    )
    target = GitTarget.model_validate(
        document(url, "refs/heads/main", subdir="src", **options)["grants"][0]["target"]
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("I/O in decision")

    with monkeypatch.context() as checks:
        for owner, name in [
            (builtins, "open"),
            (io, "open"),
            (os, "open"),
            (os, "stat"),
            (os, "getcwd"),
            (subprocess, "Popen"),
            (socket, "socket"),
        ]:
            checks.setattr(owner, name, forbidden)
        result = decide_git(selected, target)
    assert result.code == code


@pytest.mark.parametrize("command", COMMANDS)
def test_local_operator_option_not_ignored(command, tmp_path, monkeypatch):
    traps(monkeypatch)
    with pytest.raises(SystemExit) as error:
        main([*command, str(tmp_path), "--operator-policy", "absent.json"])
    assert error.value.code == 2


def test_ca_refusal_and_typed_object_revalidation(monkeypatch):
    url = "https://git.example/team/project.git"
    selected = policy(url, "main", ca_file=Path("/trust/ca.pem"))
    traps(monkeypatch)
    with pytest.raises(AuthorizationDenied, match="operator_git_source_denied"):
        with acquire_snapshot(
            url, "main", ca_file=Path("/trust/other.pem"), operator_policy=selected
        ):
            pytest.fail("accepted")
    target = selected.grants[0].target.model_copy(
        update={"repository": "file:///secret"}
    )
    assert decide_git(selected, target).code == "operator_arguments_invalid"
    broken = selected.model_copy(
        update={"grants": (selected.grants[0].model_copy(update={"target": target}),)}
    )
    assert decide_git(broken, target).code == "operator_policy_invalid"
    with pytest.raises(AuthorizationDenied, match="operator_arguments_invalid"):
        with acquire_snapshot(
            url, "main", ca_file="/trust/ca.pem", operator_policy=selected
        ):
            pytest.fail("accepted")


def test_snapshot_keeps_captured_parameters(remote, tls, scratch, monkeypatch):
    import apizr.operator_policy as operator

    url, _, commit = remote
    kwargs = {"subdir": "service", "ca_file": tls[0], "limits": AcquisitionLimits()}
    selected = policy(url, "main", **kwargs)
    original = operator.decide_git

    def substitute(grants, target):
        result = original(grants, target)
        kwargs.update(subdir="missing", ca_file=Path("/does-not-exist"))
        object.__setattr__(kwargs["limits"], "max_snapshot_bytes", 1)
        object.__setattr__(
            selected.grants[0].target, "repository", "https://other.example/repo"
        )
        return result

    monkeypatch.setattr(operator, "decide_git", substitute)
    with acquire_snapshot(url, "main", operator_policy=selected, **kwargs) as snapshot:
        assert snapshot.commit == commit and snapshot.subdir == "service"
    assert not snapshot.root.exists() and not list(scratch.iterdir())


def test_git_rule_strict_and_separate_from_plugin_rights():
    raw = document("https://git.example/repo", "main")
    for update in (
        {"permissions": ["registry.read"]},
        {"permissions": ["git.fetch", "git.fetch"]},
        {"plugin": {}},
        {"adapter": "forge"},
    ):
        invalid = copy.deepcopy(raw)
        invalid["grants"][0].update(update)
        with pytest.raises(ValueError):
            OperatorPolicy.model_validate_json(json.dumps(invalid))


@pytest.mark.parametrize("transport", ["https", "ssh"])
def test_complete_documented_git_policy(transport):
    path = (
        Path(__file__).resolve().parents[2]
        / f"docs/examples/operator-git-{transport}.json"
    )
    selected = OperatorPolicy.model_validate_json(path.read_bytes())
    assert len(selected.grants) == 1
    assert decide_git(selected, selected.grants[0].target).allowed


@pytest.mark.parametrize(
    "left,right",
    [
        (
            "https://git.example/team/project.git",
            "https://git.example/team/project.git-other",
        ),
        (
            "https://git.example/team/project.git",
            "https://git.example/team/%70roject.git",
        ),
        (
            "https://git.example/team/project.git",
            "https://git.example/team%2Fproject.git",
        ),
        (
            "https://git.example/team/project.git",
            "https://git.example:443/team/project.git",
        ),
        (
            "https://git.example/team/project.git",
            "https://GIT.example/team/project.git",
        ),
        ("git@git.example:team/project.git", "git@git.example:/team/project.git"),
        ("git@git.example:team/project.git", "ssh://git@git.example/team/project.git"),
        (
            "ssh://git@git.example/team/project.git",
            "ssh://git@git.example:22/team/project.git",
        ),
        (
            "ssh://git@git.example/team/project.git",
            "ssh://other@git.example/team/project.git",
        ),
    ],
)
def test_addresses_are_not_equated(left, right):
    options = {} if left.startswith("https://") else inputs("ssh")[1]
    selected = policy(left, "main", **options)
    target = GitTarget.model_validate(
        document(right, "main", **options)["grants"][0]["target"]
    )
    assert decide_git(selected, target).code == "operator_git_source_denied"


def test_relative_trust_references_captured_without_resolving(tmp_path, monkeypatch):
    import apizr.operator_policy as operator

    monkeypatch.chdir(tmp_path)
    selected = policy(
        "git@host:repo",
        "main",
        ssh_agent_socket=Path("agent"),
        ssh_known_hosts=Path("keys/../known"),
    )

    def stop(grants, target):
        assert target.ssh_agent_socket == str(tmp_path / "agent")
        assert target.ssh_known_hosts == str(tmp_path / "keys/../known")
        assert operator.decide_git is stop
        assert grants.grants[0].target == target
        raise RuntimeError("captured")

    traps(monkeypatch)
    monkeypatch.setattr(operator, "decide_git", stop)
    with pytest.raises(RuntimeError, match="captured"):
        with acquire_snapshot(
            "git@host:repo",
            "main",
            ssh_agent_socket=Path("agent"),
            ssh_known_hosts=Path("keys/../known"),
            operator_policy=selected,
        ):
            pytest.fail("acquired")

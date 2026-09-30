"""Exact authority, exclusive publication, and read-only local diagnostics."""

import json
import os
import socket
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import pytest
from batch_inputs import request as batch_request

from apizr.analysis_contracts import LocalTarget
from apizr.cli import main
from apizr.exposure.policy import ExposurePolicy
from apizr.local_plugins import activation, store
from apizr.local_plugins.models import Installation, Inventory
from apizr.onboarding import (
    InitError,
    diagnostics,
    doctor,
    initialization,
    initialize_project,
    plan_initialization,
)
from apizr.operator_policy import OperatorPolicy, PluginIdentity, decide_analysis
from apizr.project import load_project
from apizr.repository_readiness.policy import RepositoryReadinessPolicy


def snapshot(root):
    return {
        str(p.relative_to(root)): (
            p.lstat().st_mode,
            p.lstat().st_mtime_ns,
            p.read_bytes()
            if p.is_file() and not p.is_symlink()
            else os.readlink(p)
            if p.is_symlink()
            else None,
        )
        for p in root.rglob("*")
    }


@pytest.fixture
def initialized(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    initialize_project(project)
    return project


@pytest.fixture
def unix_socket():
    with tempfile.TemporaryDirectory(prefix="apizr-dx-", dir="/tmp") as directory:
        path = Path(directory).resolve() / "socket"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.bind(str(path))
            yield path


def checks(project, **kwargs):
    result = doctor(
        project=project / "apizr.toml",
        operator_policy=project / ".apizr/operator.json",
        **kwargs,
    )
    return result, {c.code: c.status for c in result.checks}


def test_plan_contract_authority_and_location_independence(tmp_path):
    first = plan_initialization(tmp_path / "one")
    second = plan_initialization(tmp_path / "two")
    assert set(first) == {
        "apizr.toml",
        ".apizr/.gitignore",
        ".apizr/operator.json",
        ".apizr/policies/readiness.json",
        ".apizr/policies/exposure.json",
    }
    assert {k: v for k, v in first.items() if k != ".apizr/operator.json"} == {
        k: v for k, v in second.items() if k != ".apizr/operator.json"
    }
    assert first[".apizr/operator.json"] != second[".apizr/operator.json"]
    authority = OperatorPolicy.model_validate_json(
        first[".apizr/operator.json"], strict=True
    )
    assert len(authority.grants) == 1
    assert authority.grants[0].permissions == ("source.analyze",)
    assert decide_analysis(authority, LocalTarget(root=str(tmp_path / "one"))).allowed
    assert not decide_analysis(
        authority, LocalTarget(root=str(tmp_path / "two"))
    ).allowed
    assert RepositoryReadinessPolicy.model_validate_json(
        first[".apizr/policies/readiness.json"]
    ).execution.modes == ("direct",)
    exposure = ExposurePolicy.model_validate_json(
        first[".apizr/policies/exposure.json"]
    )
    assert exposure.selection.include == () and not exposure.selection.include_all_ready
    assert exposure.interfaces == ("mcp", "rest") and exposure.execution.allowed == (
        "direct",
    )
    assert b"operator" not in first["apizr.toml"]


@pytest.mark.parametrize(
    "roots,expected",
    [((".",), (".",)), (("src", "app"), ("app", "src")), (("src", "src"), ("src",))],
)
def test_init_valid_roots(tmp_path, roots, expected):
    result = initialize_project(tmp_path, source_roots=roots)
    assert load_project(tmp_path / "apizr.toml").scan.source_roots == expected
    assert str(tmp_path) not in result.model_dump_json()
    assert result.schema_version == "apizr.init-result/v1"
    assert len(list(tmp_path.rglob("*"))) == 7
    assert (tmp_path / ".apizr/operator.json").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "roots",
    [
        (),
        ("..",),
        ("/src",),
        (".", "src"),
        ("src", "src/app"),
        ("bad\\path",),
        ("x\0",),
    ],
)
def test_init_bad_roots(tmp_path, roots):
    with pytest.raises(InitError, match="init_target_invalid"):
        initialize_project(tmp_path, source_roots=roots)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "name",
    [
        "apizr.toml",
        ".apizr",
        ".apizr/operator.json",
        ".apizr/unknown",
        ".apizr/.gitignore",
        ".apizr/policies/readiness.json",
        ".apizr/policies/exposure.json",
        ".apizr-init.stage",
    ],
)
def test_init_existing(tmp_path, name):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("user data")
    before = snapshot(tmp_path)
    with pytest.raises(InitError, match="init_output_"):
        initialize_project(tmp_path)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "kind", ["target", "parent", "config", "apizr", "missing", "file"]
)
def test_init_unsafe_targets(tmp_path, kind):
    actual = tmp_path / "actual"
    actual.mkdir()
    target = actual
    if kind in ("target", "parent"):
        target = tmp_path / "link"
        target.symlink_to(actual, target_is_directory=True)
        if kind == "parent":
            (actual / "child").mkdir()
            target = target / "child"
    elif kind in ("config", "apizr"):
        (actual / ("apizr.toml" if kind == "config" else ".apizr")).symlink_to(
            tmp_path / "missing"
        )
    elif kind == "missing":
        target = tmp_path / "missing"
    else:
        target = tmp_path / "file"
        target.write_text("keep")
    before = snapshot(tmp_path)
    with pytest.raises(InitError):
        initialize_project(target)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("error", [PermissionError, KeyboardInterrupt])
@pytest.mark.parametrize("phase", ["write", "link", "commit"])
def test_init_interruption(tmp_path, monkeypatch, error, phase):
    def fail(*a, **k):
        raise error()

    if phase == "write":
        monkeypatch.setattr(initialization, "_write", fail)
    else:
        link = os.link

        def guarded(src, dst, **kw):
            if (dst == "apizr.toml") == (phase == "commit"):
                raise error()
            return link(src, dst, **kw)

        monkeypatch.setattr(initialization.os, "link", guarded)
    with pytest.raises(InitError):
        initialize_project(tmp_path)
    assert not list(tmp_path.iterdir())


def test_interrupt_after_commit_keeps_valid_configuration(tmp_path, monkeypatch):
    link = os.link

    def interrupted(src, dst, **kw):
        link(src, dst, **kw)
        if dst == "apizr.toml":
            raise KeyboardInterrupt()

    monkeypatch.setattr(initialization.os, "link", interrupted)
    with pytest.raises(InitError, match="init_cancelled"):
        initialize_project(tmp_path)
    assert checks(tmp_path)[0].exit_code == 0
    assert not (tmp_path / initialization.STAGE).exists()


def test_nested_gitignore(initialized):
    subprocess.run(["git", "init", "-q", str(initialized)], check=True)
    p = subprocess.run(
        [
            "git",
            "-C",
            str(initialized),
            "check-ignore",
            "--no-index",
            ".apizr/operator.json",
            ".apizr/policies/readiness.json",
            ".apizr/policies/exposure.json",
        ],
        capture_output=True,
        text=True,
    )
    assert p.stdout == ".apizr/operator.json\n"
    assert not (initialized / ".gitignore").exists()


def test_doctor_healthy_readonly_and_no_effects(initialized, monkeypatch):
    (initialized / "evil.py").write_text('raise RuntimeError("MUST_NOT_EXECUTE")')
    before = snapshot(initialized)

    def forbidden(*a, **k):
        pytest.fail("doctor attempted an effect")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(store, "installation_lock", forbidden)
    monkeypatch.setattr(activation, "run_extension", forbidden)
    monkeypatch.setenv("APIZR_SECRET", "SENTINEL_PRIVATE_SECRET")
    result, status = checks(initialized)
    assert result.exit_code == 0 and status["exposure_selection"] == "warn"
    assert status["analysis_authority"] == "pass"
    assert snapshot(initialized) == before
    assert str(initialized) not in result.model_dump_json()
    assert "SENTINEL" not in result.model_dump_json()
    assert result == checks(initialized)[0]


def test_no_authority_discovery(initialized):
    result = doctor(project=initialized / "apizr.toml")
    assert result.exit_code == 0
    assert (
        next(c for c in result.checks if c.code == "analysis_authority").status
        == "warn"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "project",
        "readiness",
        "exposure",
        "operator",
        "wrong-root",
        "symlink-root",
        "missing-root",
        "missing-policy",
        "duplicate-json",
        "oversize",
        "malformed-utf8",
        "policy-link",
    ],
)
def test_doctor_bad_configuration(initialized, fault, tmp_path):
    p = initialized / "apizr.toml"
    if fault == "project":
        p.write_text('schema_version = "wrong"')
    elif fault in ("readiness", "exposure"):
        (initialized / f".apizr/policies/{fault}.json").write_text(
            '{"unexpected":true}'
        )
    elif fault in ("operator", "duplicate-json", "oversize", "malformed-utf8"):
        (initialized / ".apizr/operator.json").write_bytes(
            {
                "operator": b"{}",
                "duplicate-json": b'{"schema":1,"schema":2}',
                "oversize": b"x" * 65537,
                "malformed-utf8": b"\xff",
            }[fault]
        )
    elif fault == "wrong-root":
        operator = json.loads((initialized / ".apizr/operator.json").read_text())
        operator["grants"][0]["target"]["root"] = str(tmp_path)
        (initialized / ".apizr/operator.json").write_text(json.dumps(operator))
    elif fault in ("symlink-root", "missing-root"):
        selected = tmp_path / "selected"
        if fault == "symlink-root":
            selected.symlink_to(initialized, target_is_directory=True)
        p.write_text(p.read_text().replace('root = "."', f'root = "{selected}"'))
    elif fault == "missing-policy":
        (initialized / ".apizr/policies/readiness.json").unlink()
    else:
        policy = initialized / ".apizr/policies/readiness.json"
        policy.unlink()
        policy.symlink_to(tmp_path / "absent")
    before = snapshot(tmp_path)
    result, _ = checks(initialized)
    assert result.exit_code == 1 and str(tmp_path) not in result.model_dump_json()
    assert snapshot(tmp_path) == before


def plugin_store(root, kinds=("mcp", "oci", "attest")):
    root.mkdir(mode=0o700)
    records = []
    for index, kind in enumerate(kinds, 1):
        ident = f"{index:032x}"
        python = root / "environments" / ident / "venv/bin/python"
        python.parent.mkdir(parents=True)
        python.symlink_to(Path(sys.executable).resolve())
        records.append(
            Installation(
                schema="apizr.extension-manifest/v1",
                name=f"outerspace-apizr-{kind}",
                version=version("outerspace-apizr"),
                module=diagnostics.MODULES[kind],
                protocol="apizr.extension/v1",
                sha256="a" * 64,
                environment_id=ident,
                python=str(python),
                lock_sha256="b" * 64,
                dependencies=[
                    {
                        "name": "outerspace-apizr",
                        "version": version("outerspace-apizr"),
                        "sha256": "c" * 64,
                    }
                ],
            )
        )
    store.publish(root, Inventory(installations=records))
    activation._publish(root, records)
    return records


@pytest.mark.parametrize("profile", ["mcp", "oci"])
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "absent",
        "inactive",
        "binding",
        "interpreter",
        "version",
        "dependency",
        "module",
    ],
)
def test_plugin_profiles(initialized, tmp_path, profile, fault, monkeypatch):
    root = tmp_path / "plugins"
    if fault != "absent":
        records = plugin_store(root, (profile,))
        record = records[0]
        if fault == "inactive":
            activation._publish(root, [])
        if fault == "binding":
            activation._publish(root, [record.model_copy(update={"sha256": "d" * 64})])
        if fault == "interpreter":
            Path(record.python).unlink()
        if fault in ("version", "dependency", "module"):
            change = (
                {"version": "9.0"}
                if fault == "version"
                else {"dependencies": []}
                if fault == "dependency"
                else {"module": "wrong"}
            )
            records = [record.model_copy(update=change)]
            store.publish(root, Inventory(installations=records))
            activation._publish(root, records)
    before = snapshot(tmp_path)

    def forbidden(*a, **k):
        pytest.fail("effect")

    monkeypatch.setattr(store, "installation_lock", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result, status = checks(initialized, profiles=(profile,), plugins_dir=root)
    assert (result.exit_code == 0) == (fault is None)
    assert status[f"{profile}_plugin_active"] == ("pass" if fault is None else "fail")
    assert snapshot(tmp_path) == before
    assert checks(initialized)[0].exit_code == 0


@pytest.mark.parametrize("installed", [False, True])
def test_clients_profile(initialized, monkeypatch, installed):
    monkeypatch.setattr(diagnostics, "available", lambda *a: installed)
    result, status = checks(initialized, profiles=("clients",))
    assert status["clients_extra_available"] == ("pass" if installed else "fail")
    assert result.exit_code == int(not installed)
    assert checks(initialized)[0].exit_code == 0


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("granted", [False, True])
def test_delivery_decisions_without_secret_reads(
    initialized, tmp_path, monkeypatch, required, granted, unix_socket
):
    records = plugin_store(tmp_path / "plugins", ("oci", "attest"))
    inputs = batch_request(tmp_path, required=required, count=2).model_dump(
        mode="json", by_alias=True
    )
    tool = tmp_path / "tool"
    tool.write_text("NOT EXECUTABLE CODE")
    tool.chmod(0o700)
    secret = tmp_path / "private-key"
    secret.write_text("SENTINEL_DO_NOT_READ")
    trust = tmp_path / "trust"
    trust.mkdir()
    grants = []
    for item in inputs["destinations"]:
        push = item["push"]
        push["docker"] = {"executable": str(tool), "socket": str(unix_socket)}
        push["authentication"] = {"config_file": str(secret), "ca_file": str(secret)}
        repository = push["destination"].rsplit(":", 1)[0]
        for op, kind in [
            ("push", 0),
            ("observe", 0),
            *([("attest", 1), ("publish", 1), ("admit", 1)] if required else []),
        ]:
            grant = {
                "plugin": PluginIdentity.from_installation(records[kind]).model_dump(
                    mode="json"
                ),
                "operation": op,
                "repository": repository,
                "permissions": ["registry.read"]
                if op == "observe"
                else ["registry.read", "registry.publish"],
            }
            if op == "attest":
                grant.update(
                    key_id="e" * 32,
                    expected_signer="e" * 64,
                    key_file=str(secret),
                    tsa_url="https://tsa.example/timestamp",
                    permissions=["registry.read", "receipt.sign", "timestamp.request"],
                )
            grants.append(grant)
        if required:
            proof = item["proof"]
            proof["verification"]["trust_store"] = str(trust)
            proof["verification"]["tool"]["executable"] = str(tool)
            proof["signing"]["key_file"] = str(secret)
            proof["transport"]["tool"]["executable"] = str(tool)
            proof["transport"]["authentication"] = {"config_file": str(secret)}
    request_file = tmp_path / "delivery.json"
    request_file.write_text(json.dumps(inputs))
    if granted:
        p = initialized / ".apizr/operator.json"
        policy = json.loads(p.read_text())
        policy["grants"] += grants
        p.write_text(json.dumps(policy))
    before = snapshot(tmp_path)
    original = os.open

    def guarded(path, *a, **kw):
        if Path(path).name == secret.name:
            pytest.fail("secret content opened")
        if a and (a[0] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)):
            pytest.fail("write attempted")
        return original(path, *a, **kw)

    with monkeypatch.context() as m:
        m.setattr(os, "open", guarded)
        m.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("tool execution"))
        m.setattr(socket, "socket", lambda *a, **k: pytest.fail("network"))
        result, status = checks(
            initialized,
            profiles=("delivery",),
            plugins_dir=tmp_path / "plugins",
            delivery_request=request_file,
        )
    assert result.exit_code == int(not granted), result
    assert status["delivery_evidence"] == "pass"
    assert status["destination_1_push"] == ("pass" if granted else "fail")
    assert not (tmp_path / "evidence").exists()
    assert snapshot(tmp_path) == before
    assert (
        "SENTINEL" not in result.model_dump_json()
        and str(tmp_path) not in result.model_dump_json()
    )


def test_cli(initialized, capsys, monkeypatch, tmp_path):
    assert main(["doctor", "--project", str(initialized / "apizr.toml"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == "apizr.doctor/v1"
    assert main(["doctor", "--project", str(initialized / "apizr.toml")]) == 0
    assert "WARN" in capsys.readouterr().out
    target = tmp_path / "new"
    target.mkdir()
    assert main(["init", str(target), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "created"
    assert main(["init", str(target)]) == 2
    assert "init_output_exists" in capsys.readouterr().err
    assert main(["doctor", "--delivery-request", "unused"]) == 2
    assert "doctor_arguments_invalid" in capsys.readouterr().err
    from apizr import onboarding_cli

    def cancelled(**kw):
        raise KeyboardInterrupt()

    monkeypatch.setattr(onboarding_cli, "doctor", cancelled)
    assert main(["doctor"]) == 130


@pytest.mark.parametrize(
    "fault", ["missing", "bad", "evidence-link", "missing-references"]
)
def test_delivery_refusals(initialized, tmp_path, fault):
    request_file = tmp_path / "request.json"
    value = batch_request(tmp_path, required=False, count=1)
    request_file.write_text(value.model_dump_json(by_alias=True))
    if fault == "bad":
        request_file.write_text("{}")
    if fault == "evidence-link":
        (tmp_path / "evidence").symlink_to(initialized, target_is_directory=True)
    result, states = checks(
        initialized,
        profiles=("delivery",),
        delivery_request=None if fault == "missing" else request_file,
    )
    assert result.exit_code == 1
    if fault in ("missing", "bad"):
        assert states["delivery_request"] == "fail"
    elif fault == "evidence-link":
        assert states["delivery_evidence"] == "fail"
    else:
        assert states["destination_1_references"] == "fail"


def test_clients_bundle_readonly(initialized, tmp_path):
    from apizr.generators.rest import generate
    from apizr.inspection import inspect_source

    source = b"def f(x: int) -> int:\n    return x\n"
    bundle = tmp_path / "bundle"
    generate(inspect_source(source, module_name="sample"), source, bundle)
    before = snapshot(tmp_path)
    result, states = checks(initialized, profiles=("clients",), bundle=bundle)
    assert result.exit_code == 0 and states["clients_bundle"] == "pass"
    assert snapshot(tmp_path) == before
    (bundle / "openapi.json").write_text("{}")
    result, states = checks(initialized, profiles=("clients",), bundle=bundle)
    assert result.exit_code == 1 and states["clients_bundle"] == "fail"


def test_init_bounds_and_human_output(tmp_path, capsys):
    for roots in (("x" * 257,), tuple(f"r{i}" for i in range(129))):
        with pytest.raises(InitError):
            initialize_project(tmp_path, source_roots=roots)
    assert main(["init", str(tmp_path)]) == 0
    assert "apizr doctor --project apizr.toml" in capsys.readouterr().out


def test_concurrent_creation_not_overwritten(tmp_path, monkeypatch):
    link = os.link

    def concurrent(src, dst, **kwargs):
        if dst == "apizr.toml":
            (tmp_path / "apizr.toml").write_text("user content")
        return link(src, dst, **kwargs)

    monkeypatch.setattr(initialization.os, "link", concurrent)
    with pytest.raises(InitError, match="init_output_conflict"):
        initialize_project(tmp_path)
    assert (tmp_path / "apizr.toml").read_text() == "user content"
    assert {p.name for p in tmp_path.iterdir()} == {"apizr.toml"}


def test_current_python_and_metadata_checks(initialized, monkeypatch):
    from importlib.metadata import PackageNotFoundError

    def unsupported(*a):
        raise ValueError()

    monkeypatch.setattr(diagnostics, "validate_python_target", unsupported)

    def missing(*a):
        raise PackageNotFoundError()

    monkeypatch.setattr(diagnostics, "version", missing)
    result, states = checks(initialized)
    assert result.exit_code == 1
    assert states["python"] == states["core_package"] == "fail"

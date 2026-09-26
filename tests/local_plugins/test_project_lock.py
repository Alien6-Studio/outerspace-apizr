"""Artifact validation, record comparison and installation are separate proofs."""

import hashlib
import json
import os
import shutil
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from apizr import mcp_cli
from apizr.cli import main
from apizr.config_files import read_regular
from apizr.local_plugins import enable_extension, install_extension
from apizr.plugin_lock import LockError, check_lock, create_lock, operations
from apizr.project import load_project
from apizr.user_config import load_user_config, plugins_directory

pytestmark = pytest.mark.timeout(30)


def declaration(name, version, digest, requirements=None):
    value = (
        f'\n[[plugins]]\nname = "{name}"\nversion = "{version}"\nsha256 = "{digest}"\n'
    )
    if requirements:
        value += f'requirements = "{requirements}"\n'
    return value


@pytest.fixture
def setup(chain, tmp_path):
    plugin, digest, requirements, wheels = chain
    shutil.copyfile(plugin, wheels / plugin.name)
    project = tmp_path / "apizr.toml"
    project.write_text(
        'schema_version = "apizr.project/v1"\n'
        + declaration("local-probe", "1.0", digest, requirements.name)
    )
    return project, wheels, tmp_path / "apizr.plugins.lock.json"


def codes(result):
    return {item.code for item in result.diagnostics}


def test_declarations_are_passive(setup, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("side effect")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(operations, "list_extensions", forbidden)
    project, wheels, output = setup
    for wheel in wheels.iterdir():
        wheel.unlink()
    (project.parent / "requirements.lock").unlink()
    config = load_project(project)
    assert config.plugins[0].name == "local-probe"
    assert not output.exists()


def test_deterministic_portable_read_only(setup, tmp_path, monkeypatch):
    project, wheels, output = setup

    def forbidden(*a, **k):
        raise AssertionError("network/execution/store access")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(operations, "list_extensions", forbidden)
    first = create_lock(*setup)
    assert first.valid
    data = output.read_bytes()
    stamp = output.stat().st_mtime_ns
    assert create_lock(*setup) == first
    assert output.stat().st_mtime_ns == stamp
    assert check_lock(project, output, wheels).valid
    copy = tmp_path / "elsewhere"
    copy.mkdir()
    for path in (project, project.parent / "requirements.lock"):
        shutil.copyfile(path, copy / path.name)
    other = copy / "wheels"
    other.mkdir()
    for path in reversed(list(wheels.iterdir())):
        shutil.copyfile(path, other / path.name)
    monkeypatch.chdir(copy)
    assert create_lock(Path(project.name), other, copy / output.name).valid
    assert (copy / output.name).read_bytes() == data
    for forbidden_value in (
        str(tmp_path),
        "environment_id",
        "activations",
        "python/bin",
        "token",
    ):
        assert forbidden_value not in data.decode()
    assert first.lock_sha256 == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    "case", ["declaration", "requirements-comment", "requirements-order", "target"]
)
def test_drift_without_rewriting(setup, case):
    project, wheels, output = setup
    assert create_lock(*setup).valid
    if case == "declaration":
        project.write_text(
            project.read_text().replace('version = "1.0"', 'version = "2.0"')
        )
    elif case == "target":
        data = json.loads(output.read_bytes())
        data["target"]["python"] = "3.99.0"
        output.write_text(json.dumps(data))
    else:
        req = project.parent / "requirements.lock"
        req.write_text(
            req.read_text() + "# new comment\n"
            if case.endswith("comment")
            else "\n".join(reversed(req.read_text().splitlines())) + "\n"
        )
    before = output.read_bytes()
    result = check_lock(project, output, wheels)
    assert not result.valid
    assert output.read_bytes() == before
    assert (
        "target_mismatch"
        if case == "target"
        else "plugin_requirements_mismatch"
        if case == "declaration"
        else "project_artifacts_changed"
    ) in codes(result)


@pytest.mark.parametrize(
    "case,code",
    [
        ("missing", "missing_wheel"),
        ("ambiguous", "ambiguous_wheel"),
        ("modified", "hash_mismatch"),
    ],
)
def test_artifact_divergence(setup, case, code):
    project, wheels, output = setup
    leaf = next(wheels.glob("locked_leaf*"))
    if case == "missing":
        leaf.unlink()
    elif case == "modified":
        leaf.write_bytes(b"different")
    else:
        shutil.copyfile(leaf, wheels / leaf.name.replace("-py3-", "-1-py3-"))
    result = create_lock(*setup)
    assert not result.valid and code in codes(result)
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        'plugins_dir = "/tmp/store"',
        'user_config = "operator.toml"',
        "activate = true",
        'permissions = ["publish"]',
        'token = "secret"',
        'python = "/bin/python"',
        'module = "evil"',
    ],
)
def test_project_cannot_grant_authority(setup, mutation):
    project = setup[0]
    project.write_text(project.read_text() + mutation + "\n")
    with pytest.raises(LockError, match="invalid_project"):
        create_lock(*setup)


@pytest.mark.parametrize(
    "replacement",
    [
        ('name = "local-probe"', 'name = "Local_Probe"'),
        ('version = "1.0"', 'version = "*"'),
        ('version = "1.0"', 'version = ">=1.0"'),
        ('requirements = "requirements.lock"', 'requirements = "../requirements.lock"'),
        ('requirements = "requirements.lock"', 'requirements = "/requirements.lock"'),
        ('requirements = "requirements.lock"', 'requirements = "https://secret/lock"'),
    ],
)
def test_invalid_declarations(setup, replacement):
    setup[0].write_text(setup[0].read_text().replace(*replacement))
    with pytest.raises(LockError, match="invalid_project"):
        create_lock(*setup)


def test_duplicate_names_and_hash_invalid(setup):
    project = setup[0]
    original = project.read_text()
    project.write_text(original + original[original.index("[[plugins]]") :])
    with pytest.raises(LockError):
        create_lock(*setup)
    project.write_text(original.replace('sha256 = "', 'sha256 = "INVALID'))
    with pytest.raises(LockError):
        create_lock(*setup)


@pytest.mark.parametrize("kind", ["fifo", "symlink", "parent-symlink"])
@pytest.mark.parametrize("input_name", ["project", "requirements", "wheel", "lock"])
def test_special_files_and_links(setup, tmp_path, kind, input_name):
    project, wheels, output = setup
    assert create_lock(*setup).valid
    path = {
        "project": project,
        "requirements": project.parent / "requirements.lock",
        "wheel": next(wheels.glob("locked_leaf*")),
        "lock": output,
    }[input_name]
    saved = path.rename(tmp_path / "saved")
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "symlink":
        path.symlink_to(saved)
    else:
        if input_name != "wheel":
            path.symlink_to(saved)  # parent traversal is exercised separately below
        else:
            original = wheels.rename(tmp_path / "original-wheels")
            wheels.symlink_to(original, target_is_directory=True)
    with pytest.raises(LockError):
        check_lock(project, output, wheels)


@pytest.mark.parametrize(
    "bound,value,code",
    [
        ("MAX_FILES", 1, "too_many_wheelhouse_files"),
        ("MAX_DOCUMENT_BYTES", 10, "lock_too_large"),
    ],
)
def test_new_limits(setup, monkeypatch, bound, value, code):
    monkeypatch.setattr(operations, bound, value)
    with pytest.raises(LockError, match=code):
        create_lock(*setup)
    assert not setup[2].exists()


@pytest.mark.parametrize("field", ["MAX_TOTAL_BYTES", "MAX_TOTAL_EXPANDED_BYTES"])
def test_existing_volume_limits(setup, monkeypatch, field):
    monkeypatch.setattr(operations.locking, field, 1)
    with pytest.raises(LockError, match="wheelhouse_too_large"):
        create_lock(*setup)


def test_concurrent_publish_conflict_and_interruption(setup, monkeypatch):
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(
            result.valid for result in pool.map(lambda _: create_lock(*setup), range(2))
        )
    output = setup[2]
    original = output.read_bytes()
    output.write_bytes(b"old-content")
    with pytest.raises(LockError, match="output_conflict"):
        create_lock(*setup)
    assert output.read_bytes() == b"old-content"
    output.unlink()

    def interrupt(*a, **k):
        raise KeyboardInterrupt()

    with monkeypatch.context() as context:
        context.setattr(operations.os, "link", interrupt)
        with pytest.raises(KeyboardInterrupt):
            create_lock(*setup)
    assert not output.exists() and not list(output.parent.glob(".apizr-lock-*"))
    assert create_lock(*setup).valid and output.read_bytes() == original


def test_retained_wheel_not_substituted(setup, monkeypatch):
    inspect = operations.inspect_dependency
    seen = []

    def replace(path, digest):
        result = inspect(path, digest)
        (setup[1] / path.name).write_bytes(b"changed after validation")
        seen.append(path)
        return result

    monkeypatch.setattr(operations, "inspect_dependency", replace)
    assert create_lock(*setup).valid and seen
    assert "hash_mismatch" in codes(check_lock(setup[0], setup[2], setup[1]))


def test_inventory_match_inactive_and_mismatch(setup, chain, tmp_path):
    project, wheels, output = setup
    root = tmp_path / "store"
    assert create_lock(*setup).valid
    assert "installation_missing" in codes(
        check_lock(project, output, wheels, installed=True, directory=root)
    )
    assert not root.exists()
    record = install_extension(
        chain[0], chain[1], requirements=chain[2], wheelhouse=wheels, directory=root
    )
    before = {p.name: p.read_bytes() for p in root.glob("*.json")}
    result = check_lock(project, output, wheels, installed=True, directory=root)
    assert (
        result.valid and result.installed[0].matches and not result.installed[0].active
    )
    assert before == {p.name: p.read_bytes() for p in root.glob("*.json")}
    enable_extension(record.name, record.version, directory=root)
    assert (
        check_lock(project, output, wheels, installed=True, directory=root)
        .installed[0]
        .active
    )
    data = json.loads((root / "installations.json").read_bytes())
    data["installations"][0]["sha256"] = "a" * 64
    (root / "installations.json").write_text(json.dumps(data))
    (root / "activations.json").unlink()
    assert "installation_mismatch" in codes(
        check_lock(project, output, wheels, installed=True, directory=root)
    )


def test_two_independent_closures(wheel_factory, tmp_path):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    project = tmp_path / "apizr.toml"
    text = 'schema_version = "apizr.project/v1"\n'
    for name, version in [("first-plugin", "1.0"), ("second-plugin", "2.0")]:
        leaf, leaf_hash = wheel_factory(
            name="shared-leaf", version=version, plugin=False
        )
        plugin, digest = wheel_factory(
            name=name, metadata_extra=f"Requires-Dist: shared-leaf=={version}\n"
        )
        leaf.rename(wheels / leaf.name)
        plugin.rename(wheels / plugin.name)
        requirements = tmp_path / (name + ".lock")
        requirements.write_text(
            f"{name}==1.0 --hash=sha256:{digest}\nshared-leaf=={version} --hash=sha256:{leaf_hash}\n"
        )
        text += declaration(name, "1.0", digest, requirements.name)
    project.write_text(text)
    output = tmp_path / "output.json"
    assert create_lock(project, wheels, output).valid
    document = json.loads(output.read_bytes())
    assert [item["dependencies"][0]["version"] for item in document["plugins"]] == [
        "1.0",
        "2.0",
    ]
    assert check_lock(project, output, wheels).valid


def test_user_preferences_cli_precedence_and_mcp(tmp_path, monkeypatch, capsys):
    config = tmp_path / "user.toml"
    config.write_text('schema_version = "apizr.user/v1"\nplugins_dir = "store"\n')
    assert load_user_config(config).plugins_dir == tmp_path / "store"
    assert plugins_directory(Path("/explicit"), config) == Path("/explicit")
    assert plugins_directory(None, None) is None
    assert main(["plugins", "list", "--user-config", str(config), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["installations"] == []
    assert not (tmp_path / "store").exists()
    seen = []

    def refuse(name, directory, inherit):
        seen.append(directory)
        raise operations.PluginError("plugin_not_installed")

    monkeypatch.setattr(mcp_cli, "admitted_extension", refuse)
    for extra in ([], ["--plugins-dir", "/explicit"]):
        assert (
            main(
                [
                    "mcp",
                    "serve",
                    "--project",
                    "/project/apizr.toml",
                    "--user-config",
                    str(config),
                    *extra,
                ]
            )
            == 2
        )
    assert seen == [tmp_path / "store", Path("/explicit")]


@pytest.mark.parametrize(
    "text",
    [
        'schema_version = "unknown"',
        'schema_version = "apizr.user/v1"\nunknown = true',
        'schema_version = "apizr.user/v1"\nplugins_dir = 12',
        'schema_version = "apizr.user/v1"\nplugins_dir = "https://secret"',
        "x" * 65537,
    ],
)
def test_invalid_user_preferences(tmp_path, text, capsys):
    path = tmp_path / "user.toml"
    path.write_text(text)
    assert main(["plugins", "list", "--user-config", str(path)]) == 2
    assert capsys.readouterr().err == "apizr plugins: invalid_user_config\n"


def test_cli_codes_and_json(setup, capsys):
    project, wheels, output = setup
    common = ["--project", str(project), "--wheelhouse", str(wheels), "--json"]
    assert main(["plugins", "lock", "create", *common, "--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    assert main(["plugins", "lock", "check", *common, "--lock", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    next(wheels.glob("locked_leaf*")).unlink()
    assert main(["plugins", "lock", "check", *common, "--lock", str(output)]) == 1
    assert not json.loads(capsys.readouterr().out)["valid"]
    output.write_text('{"schema_version":1,"schema_version":2}')
    assert main(["plugins", "lock", "check", *common, "--lock", str(output)]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["diagnostics"][0]["code"] == "invalid_project_lock"
    assert str(project) not in captured.err


def test_bounded_reads(tmp_path):
    path = tmp_path / "file"
    path.write_bytes(b"123")
    with pytest.raises(ValueError, match="file_too_large"):
        read_regular(path, 2)


@pytest.mark.parametrize(
    "case,code",
    [
        ("manifest", "invalid_manifest"),
        ("protocol", "invalid_manifest"),
        ("metadata", "inconsistent_metadata"),
        ("startup", "unsupported_wheel_layout"),
        ("native", "wheel_target_not_verifiable"),
        ("invalid", "invalid_wheel"),
    ],
)
def test_verified_identity_and_archive_admission(wheel_factory, tmp_path, case, code):
    kwargs = {}
    if case == "manifest":
        kwargs["manifest_raw"] = b'{"invalid":true}'
    elif case == "protocol":
        kwargs["manifest_changes"] = {"protocol": "apizr.extension/v999"}
    elif case == "metadata":
        kwargs["manifest_changes"] = {"version": "2.0"}
    elif case == "startup":
        kwargs["files"] = {"bad.pth": b'print("must not execute")'}
    elif case == "native":
        kwargs["filename"] = "local_probe-1.0-cp39-cp39-win32.whl"
    wheel, digest = wheel_factory(**kwargs)
    if case == "invalid":
        wheel.write_bytes(b"not a zip")
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    wheel.rename(wheels / wheel.name)
    project = tmp_path / "apizr.toml"
    project.write_text(
        'schema_version = "apizr.project/v1"\n'
        + declaration("local-probe", "1.0", digest)
    )
    result = create_lock(project, wheels, tmp_path / "lock.json")
    assert not result.valid and code in codes(result)


def test_dependency_free_lock_and_no_code_import(
    wheel_factory, tmp_path, monkeypatch, capsys
):
    marker = tmp_path / "executed"
    wheel, digest = wheel_factory(
        files={
            "local_probe.py": f"from pathlib import Path\nPath({str(marker)!r}).touch()\n".encode()
        }
    )
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    wheel.rename(wheels / wheel.name)
    project = tmp_path / "apizr.toml"
    project.write_text(
        'schema_version = "apizr.project/v1"\n'
        + declaration("local-probe", "1.0", digest)
    )
    output = tmp_path / "lock.json"
    assert (
        main(
            [
                "plugins",
                "lock",
                "create",
                "--project",
                str(project),
                "--wheelhouse",
                str(wheels),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "Plugin lock valid.\n"
    assert check_lock(project, output, wheels).valid
    assert not marker.exists()
    wheel = next(wheels.iterdir())
    wheel.unlink()
    assert (
        main(
            [
                "plugins",
                "lock",
                "check",
                "--project",
                str(project),
                "--wheelhouse",
                str(wheels),
                "--lock",
                str(output),
            ]
        )
        == 1
    )
    assert "missing_wheel: local-probe / local-probe" in capsys.readouterr().out


@pytest.mark.parametrize(
    "case",
    [
        "duplicate",
        "manifest",
        "dependency-duplicate",
        "no-requirements",
        "unknown",
        "too-large",
    ],
)
def test_malformed_lock_document(setup, case, monkeypatch):
    assert create_lock(*setup).valid
    data = json.loads(setup[2].read_bytes())
    if case == "duplicate":
        data["plugins"].append(data["plugins"][0])
    elif case == "manifest":
        data["plugins"][0]["manifest"]["version"] = "9.0"
    elif case == "dependency-duplicate":
        data["plugins"][0]["dependencies"].append(data["plugins"][0]["dependencies"][0])
    elif case == "no-requirements":
        data["plugins"][0]["requirements"] = None
    elif case == "unknown":
        data["token"] = "hidden"
    else:
        monkeypatch.setattr(operations, "MAX_DOCUMENT_BYTES", 10)
    setup[2].write_text(json.dumps(data))
    with pytest.raises(LockError, match="invalid_project_lock"):
        check_lock(setup[0], setup[2], setup[1])


@pytest.mark.parametrize(
    "case,code",
    [
        ("project", "project_unreadable"),
        ("requirements", "requirements_unreadable"),
        ("lock", "lock_unreadable"),
    ],
)
def test_read_errors_distinct_from_invalid_documents(setup, case, code):
    assert create_lock(*setup).valid
    path = {
        "project": setup[0],
        "requirements": setup[0].parent / "requirements.lock",
        "lock": setup[2],
    }[case]
    path.unlink()
    with pytest.raises(LockError, match=code):
        check_lock(setup[0], setup[2], setup[1])


def test_invalid_requirements_and_inventory(setup, tmp_path):
    assert create_lock(*setup).valid
    requirements = setup[0].parent / "requirements.lock"
    previous = requirements.read_bytes()
    requirements.write_text("--index-url https://secret.invalid\n")
    with pytest.raises(LockError, match="invalid_requirements"):
        check_lock(setup[0], setup[2], setup[1])
    requirements.write_bytes(previous)
    root = tmp_path / "store"
    root.mkdir(mode=0o700)
    (root / "installations.json").write_text("{invalid")
    with pytest.raises(LockError, match="inventory_unreadable"):
        check_lock(setup[0], setup[2], setup[1], installed=True, directory=root)


def test_directory_symlink_and_oversized_config(setup, tmp_path, monkeypatch):
    link = tmp_path / "linked"
    link.symlink_to(setup[0].parent, target_is_directory=True)
    with pytest.raises(LockError, match="project_unreadable"):
        create_lock(link / setup[0].name, setup[1], setup[2])
    project = setup[0]
    project.write_text(" " * 65537)
    with pytest.raises(LockError, match="invalid_project"):
        create_lock(*setup)


def test_output_failures_and_cancellation(setup, monkeypatch, capsys):
    output = setup[2]
    with pytest.raises(LockError, match="output_unwritable"):
        create_lock(setup[0], setup[1], output / "nonexistent" / "file")

    def interrupt(*a, **k):
        raise KeyboardInterrupt()

    monkeypatch.setattr(operations.os, "link", interrupt)
    assert (
        main(
            [
                "plugins",
                "lock",
                "create",
                "--project",
                str(setup[0]),
                "--wheelhouse",
                str(setup[1]),
                "--output",
                str(output),
                "--json",
            ]
        )
        == 130
    )
    assert capsys.readouterr().err == "apizr plugins: cancelled\n"
    assert not output.exists()


def test_user_defaults_and_types(tmp_path):
    user = tmp_path / "user.toml"
    user.write_text('schema_version = "apizr.user/v1"\n')
    assert plugins_directory(None, user) is None
    assert plugins_directory(Path("/explicit"), None) == Path("/explicit")
    user.write_text('schema_version = "apizr.user/v1"\nplugins_dir = 2020-01-01\n')
    with pytest.raises(operations.PluginError, match="invalid_user_config"):
        load_user_config(user)


def test_explicit_preferences_on_lifecycle_and_override(setup, chain, tmp_path, capsys):
    store = tmp_path / "store"
    user = tmp_path / "user.toml"
    user.write_text('schema_version = "apizr.user/v1"\nplugins_dir = "store"\n')
    install_extension(
        chain[0], chain[1], requirements=chain[2], wheelhouse=setup[1], directory=store
    )
    user_args = ["--user-config", str(user)]
    arguments = tmp_path / "arguments.json"
    arguments.write_text("{}")
    assert (
        main(["plugins", "enable", "local-probe", "--version", "1.0", *user_args]) == 0
    )
    assert (
        main(
            [
                "plugins",
                "run",
                "local-probe",
                "answer",
                "--arguments",
                str(arguments),
                *user_args,
            ]
        )
        == 0
    )
    assert main(["plugins", "disable", "local-probe", *user_args]) == 0
    assert (
        main(
            [
                "plugins",
                "run",
                "local-probe",
                "answer",
                "--arguments",
                str(arguments),
                *user_args,
            ]
        )
        == 2
    )
    assert "plugin_inactive" in capsys.readouterr().err
    assert (
        main(
            [
                "plugins",
                "list",
                "--json",
                *user_args,
                "--plugins-dir",
                str(tmp_path / "other"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["installations"] == []


def test_invalid_user_file_has_json_lock_result(setup, tmp_path, capsys):
    user = tmp_path / "user.toml"
    user.write_text('schema_version = "bad"')
    assert (
        main(
            [
                "plugins",
                "lock",
                "create",
                "--project",
                str(setup[0]),
                "--wheelhouse",
                str(setup[1]),
                "--output",
                str(setup[2]),
                "--user-config",
                str(user),
                "--json",
            ]
        )
        == 2
    )
    assert (
        json.loads(capsys.readouterr().out)["diagnostics"][0]["code"]
        == "invalid_user_config"
    )


def test_unpinned_versions_and_plugin_count(setup):
    original = setup[0].read_text()
    setup[0].write_text(original.replace('version = "1.0"', 'version = "1.latest"'))
    with pytest.raises(LockError, match="invalid_project"):
        create_lock(*setup)
    setup[0].write_text(
        'schema_version = "apizr.project/v1"\n'
        + "".join(declaration(f"plugin-{i}", "1.0", "a" * 64) for i in range(33))
    )
    with pytest.raises(LockError, match="invalid_project"):
        create_lock(*setup)

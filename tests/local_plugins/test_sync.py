"""Real additive installs, retained bytes, cancellation and partial publication."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from apizr.cli import main
from apizr.extension_runtime import Limits
from apizr.local_plugins import (
    backend,
    enable_extension,
    install_extension,
    list_extensions,
    run_extension,
    store,
)
from apizr.local_plugins.control import InstallationCancelled, InstallControl
from apizr.local_plugins.models import PluginError
from apizr.plugin_lock import check_lock, create_lock
from apizr.plugin_sync import operations, probe, sync_plugins

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def project(wheel_factory, tmp_path):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    text = 'schema_version = "apizr.project/v1"\n'
    for name, version, value in [("sync-a", "1.0", 42), ("sync-b", "2.0", 73)]:
        leaf, digest = wheel_factory(
            name="sync-leaf",
            version=version,
            plugin=False,
            files={"sync_leaf.py": f"VALUE = {value}\n".encode()},
        )
        lines = [f"sync-leaf=={version} --hash=sha256:{digest}\n"]
        leaf.rename(wheels / leaf.name)
        helper, digest = wheel_factory(
            name="sync-helper",
            version=version,
            plugin=False,
            metadata_extra=f"Requires-Dist: sync-leaf=={version}\n",
            files={"sync_helper.py": b"from sync_leaf import VALUE\n"},
        )
        lines.append(f"sync-helper=={version} --hash=sha256:{digest}\n")
        helper.rename(wheels / helper.name)
        wheel, digest = wheel_factory(
            name=name,
            metadata_extra=f"Requires-Dist: sync-helper=={version}\n",
            files={
                "local_probe.py": b'import json,sys\nfrom sync_helper import VALUE\nr=json.load(sys.stdin)\nprint(json.dumps({k:r[k] for k in ("protocol","request_id","operation")}|{"status":"ok","result":VALUE}))\n'
            },
        )
        wheel.rename(wheels / wheel.name)
        lines.append(f"{name}==1.0 --hash=sha256:{digest}\n")
        (tmp_path / f"{name}.lock").write_text("".join(lines))
        text += f'\n[[plugins]]\nname = "{name}"\nversion = "1.0"\nsha256 = "{digest}"\nrequirements = "{name}.lock"\n'
    path = tmp_path / "apizr.toml"
    path.write_text(text)
    lock = tmp_path / "apizr.plugins.lock.json"
    assert create_lock(path, wheels, lock).valid
    return path, lock, wheels


def sync(project, root, **kw):
    return sync_plugins(*project, directory=root, **kw)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*.json")}


def test_dry_run_no_process_store_or_network(project, tmp_path, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("dry run side effect")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(backend, "require_uv", forbidden)
    root = tmp_path / "store"
    result = sync(project, root, dry_run=True)
    assert (
        result.exit_code == 0 and result.state == "planned" and result.mode == "dry-run"
    )
    assert [a.action for a in result.plugins] == ["install", "install"]
    assert not any(a.interpreter_verified for a in result.plugins)
    assert not root.exists()


def test_install_independent_closures_idempotence_and_invocation(
    project, tmp_path, monkeypatch
):
    root = tmp_path / "store"
    env, path = dict(os.environ), list(sys.path)
    result = sync(project, root)
    assert result.state == "complete" and result.exit_code == 0
    assert [a.status for a in result.plugins] == ["installed", "installed"]
    assert all(a.interpreter_verified and not a.active for a in result.plugins)
    assert check_lock(
        project[0], project[1], project[2], installed=True, directory=root
    ).valid
    before = snapshot(root)
    with monkeypatch.context() as context:
        context.setattr(
            backend,
            "require_uv",
            lambda: (_ for _ in ()).throw(AssertionError("uv must not be required")),
        )
        assert [a.status for a in sync(project, root).plugins] == ["reused", "reused"]
    assert (
        snapshot(root) == before and len(list((root / "environments").iterdir())) == 2
    )
    for name, expected in [("sync-a", 42), ("sync-b", 73)]:
        enable_extension(name, "1.0", directory=root)
        assert (
            run_extension(name, "answer", {}, directory=root, limits=Limits()).result
            == expected
        )
    assert dict(os.environ) == env and sys.path == path


def test_old_active_version_and_foreign_plugin_untouched(
    project, tmp_path, wheel_factory
):
    root = tmp_path / "store"
    old_wheel, old_hash = wheel_factory(name="sync-a", version="0.9")
    old = install_extension(old_wheel, old_hash, directory=root)
    other_wheel, other_hash = wheel_factory(name="foreign")
    other = install_extension(other_wheel, other_hash, directory=root)
    enable_extension(old.name, old.version, directory=root)
    before = (root / "activations.json").read_bytes()
    result = sync(project, root)
    assert result.exit_code == 0 and all(not a.active for a in result.plugins)
    assert (root / "activations.json").read_bytes() == before
    assert old in list_extensions(directory=root).installations
    assert other in list_extensions(directory=root).installations


def test_known_conflict_before_any_install(project, tmp_path, wheel_factory):
    root = tmp_path / "store"
    wheel, digest = wheel_factory(name="sync-b")
    install_extension(wheel, digest, directory=root)
    before = snapshot(root)
    for dry_run in (True, False):
        result = sync(project, root, dry_run=dry_run)
        assert result.exit_code == 1 and result.state == "refused"
        assert result.plugins[1].status == "refused"
        assert snapshot(root) == before
    assert len(list((root / "environments").iterdir())) == 1


@pytest.mark.parametrize("case", ["comment", "target", "missing", "hash"])
def test_preflight_content_refusals_no_store(project, tmp_path, case):
    if case == "comment":
        path = tmp_path / "sync-a.lock"
        path.write_text(path.read_text() + "# comment\n")
    elif case == "target":
        data = json.loads(project[1].read_bytes())
        data["target"]["python"] = "3.99.0"
        project[1].write_text(json.dumps(data))
    else:
        wheel = next(project[2].glob("sync_b-*"))
        wheel.unlink() if case == "missing" else wheel.write_bytes(b"changed")
    root = tmp_path / "store"
    result = sync(project, root)
    assert result.exit_code == 1 and not root.exists()


def test_original_substitution_after_validation(project, tmp_path, monkeypatch):
    original = operations._state
    replaced = False

    def replace(root, control):
        nonlocal replaced
        if not replaced:
            replaced = True
            project[0].write_text("broken")
            project[1].write_text("broken")
            for wheel in project[2].iterdir():
                wheel.write_bytes(b"broken")
            for req in tmp_path.glob("*.lock"):
                req.write_text("broken")
        return original(root, control)

    monkeypatch.setattr(operations, "_state", replace)
    assert sync(project, tmp_path / "store").state == "complete"


def test_partial_real_install_and_resume_same_artifacts(project, tmp_path, monkeypatch):
    root = tmp_path / "store"
    run = backend.run_uv
    calls = []

    def fail_b(executable, arguments, work, **kw):
        if arguments[0] == "pip":
            req = (work / "requirements.txt").read_text()
            calls.append(req)
            if "sync-b==" in req:
                # A real failed installer invocation, no changed lock/wheel bytes.
                return run(
                    executable, [*arguments, "--apizr-test-invalid-option"], work, **kw
                )
        return run(executable, arguments, work, **kw)

    with monkeypatch.context() as context:
        context.setattr(backend, "run_uv", fail_b)
        first = sync(project, root)
    assert first.state == "partial" and first.exit_code == 2
    assert [a.status for a in first.plugins] == ["installed", "failed"]
    assert len(list((root / "environments").iterdir())) == 1
    previous = list_extensions(directory=root).installations[0]
    second = sync(project, root)
    assert second.exit_code == 0
    assert [a.status for a in second.plugins] == ["reused", "installed"]
    assert previous in list_extensions(directory=root).installations


def test_missing_uv_and_dependency_free_plugin(tmp_path, wheel_factory, monkeypatch):
    wheel, digest = wheel_factory()
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    wheel.rename(wheels / wheel.name)
    project = tmp_path / "apizr.toml"
    project.write_text(
        f'schema_version = "apizr.project/v1"\n[[plugins]]\nname = "local-probe"\nversion = "1.0"\nsha256 = "{digest}"\n'
    )
    lock = tmp_path / "lock.json"
    assert create_lock(project, wheels, lock).valid
    inputs = project, lock, wheels
    root = tmp_path / "store"
    with monkeypatch.context() as context:
        context.setenv("PATH", "")
        refused = sync(inputs, root)
        assert refused.exit_code == 2 and refused.diagnostics[0].code == "uv_not_found"
        assert not root.exists()
    assert sync(inputs, root).exit_code == 0


@pytest.mark.parametrize("case", ["missing", "target"])
def test_unusable_reused_interpreter_before_new_install(
    project, tmp_path, monkeypatch, case
):
    root = tmp_path / "store"
    assert sync(project, root).exit_code == 0
    inventory = store.read_inventory(root)
    record = inventory.installations[0]
    before = snapshot(root)
    if case == "missing":
        Path(record.python).unlink()
    else:
        monkeypatch.setattr(
            probe,
            "PROGRAM",
            probe.PROGRAM.replace("platform.python_version()", '"3.99.0"'),
        )
    assert sync(project, root, dry_run=True).exit_code == 0
    result = sync(project, root)
    assert result.exit_code == 2 and result.state == "refused"
    assert result.diagnostics[0].code == (
        "installed_interpreter_unavailable"
        if case == "missing"
        else "installed_target_mismatch"
    )
    assert snapshot(root) == before


def test_concurrent_syncs_converge(project, tmp_path):
    root = tmp_path / "store"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: sync(project, root), range(2)))
    assert all(r.exit_code == 0 for r in results)
    assert len(list_extensions(directory=root).installations) == 2
    assert len(list((root / "environments").iterdir())) == 2


@pytest.mark.parametrize("after", [False, True])
def test_cancellation_at_publication_preserves_visible_state(
    project, tmp_path, monkeypatch, after
):
    root = tmp_path / "store"
    publish = store.publish
    event = threading.Event()

    def interrupt(root, inventory):
        if after:
            publish(root, inventory)
        event.set()
        raise InstallationCancelled()

    with monkeypatch.context() as context:
        context.setattr(store, "publish", interrupt)
        result = sync(project, root, cancel=event)
    assert result.exit_code == 130 and result.state == "interrupted"
    assert len(list_extensions(directory=root).installations) == int(after)
    assert len(list((root / "environments").iterdir())) == int(after)
    retry = sync(project, root)
    assert retry.exit_code == 0
    assert retry.plugins[0].status == ("reused" if after else "installed")


def test_unconfirmed_publication_never_removes_environment(
    project, tmp_path, monkeypatch
):
    root = tmp_path / "store"
    publish = store.publish

    def interrupt(root, inventory):
        publish(root, inventory)
        (root / "installations.json").write_bytes(b"corrupt")
        raise InstallationCancelled()

    with monkeypatch.context() as context:
        context.setattr(store, "publish", interrupt)
        result = sync(project, root)
    assert result.state == "unconfirmed" and result.exit_code == 130
    assert len(list((root / "environments").iterdir())) == 1


def test_deadline_and_cancel_store_wait_release(project, tmp_path):
    root = tmp_path / "store"
    assert sync(project, root).exit_code == 0
    with store.installation_lock(root):
        result = sync(project, root, timeout_ms=60)
        assert result.exit_code == 2 and result.diagnostics[0].code == "sync_timeout"
        cancel = threading.Event()
        cancel.set()
        assert sync(project, root, cancel=cancel).exit_code == 130
    assert sync(project, root).exit_code == 0


@pytest.mark.parametrize("cancelled", [False, True])
def test_supervised_uv_stopped_and_reaped(tmp_path, cancelled):
    marker = tmp_path / "ready"
    executable = tmp_path / "uv"
    # Readiness is signalled by the worker, not inferred from an arbitrary delay.
    executable.write_text(
        f"#!{sys.executable}\nimport os,time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n"
    )
    executable.chmod(0o700)
    event = threading.Event()
    control = InstallControl(time.monotonic() + (10 if cancelled else 0.5), event)
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(
            backend.run_uv, str(executable), [], tmp_path, control=control
        )
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            event.wait(0.01)
        assert marker.exists()
        if cancelled:
            event.set()
        with pytest.raises(
            PluginError, match="sync_cancelled" if cancelled else "sync_timeout"
        ):
            task.result(timeout=4)
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)
    # No zombie/direct child and another backend invocation still works.
    with pytest.raises(ChildProcessError):
        os.waitpid(int(marker.read_text()), os.WNOHANG)
    backend.run_uv(
        backend.require_uv(),
        ["--version"],
        tmp_path,
        control=InstallControl(time.monotonic() + 5),
    )


def test_cli_json_preferences_and_errors(project, tmp_path, capsys):
    user = tmp_path / "user.toml"
    user.write_text('schema_version = "apizr.user/v1"\nplugins_dir = "store"\n')
    args = [
        "plugins",
        "sync",
        "--project",
        str(project[0]),
        "--lock",
        str(project[1]),
        "--wheelhouse",
        str(project[2]),
        "--user-config",
        str(user),
        "--json",
    ]
    assert main([*args, "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "dry-run"
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "complete"
    user.write_text('schema_version = "invalid"')
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["state"] == "refused"


def test_uv_rejects_unsatisfied_transitive_constraint(wheel_factory, tmp_path):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    dep, digest = wheel_factory(name="sync-leaf", plugin=False)
    dep.rename(wheels / dep.name)
    requirements = f"sync-leaf==1.0 --hash=sha256:{digest}\n"
    wheel, digest = wheel_factory(metadata_extra="Requires-Dist: sync-leaf==2.0\n")
    wheel.rename(wheels / wheel.name)
    requirements += f"local-probe==1.0 --hash=sha256:{digest}\n"
    (tmp_path / "requirements.lock").write_text(requirements)
    path = tmp_path / "apizr.toml"
    path.write_text(
        f'schema_version = "apizr.project/v1"\n[[plugins]]\nname = "local-probe"\nversion = "1.0"\nsha256 = "{digest}"\nrequirements = "requirements.lock"\n'
    )
    lock = tmp_path / "lock.json"
    assert create_lock(path, wheels, lock).valid
    root = tmp_path / "store"
    assert sync_plugins(path, lock, wheels, directory=root, dry_run=True).exit_code == 0
    result = sync_plugins(path, lock, wheels, directory=root)
    assert result.state == "partial" and result.exit_code == 2
    assert result.diagnostics[0].code == "uv_install_failed"
    assert not list_extensions(directory=root).installations
    assert not list((root / "environments").iterdir())


@pytest.mark.parametrize(
    "code", ["print('invalid')", "print('x'*9000)", "raise SystemExit(1)"]
)
def test_bounded_probe_failure_and_recovery(project, tmp_path, monkeypatch, code):
    root = tmp_path / "store"
    assert sync(project, root).exit_code == 0
    with monkeypatch.context() as context:
        context.setattr(
            probe, "PROGRAM", "import sys; sys.stdin.buffer.read(1); " + code
        )
        result = sync(project, root)
        assert result.exit_code == 2 and result.state == "refused"
        assert result.diagnostics[0].code == "installed_interpreter_unavailable"
    assert sync(project, root).exit_code == 0


def test_failed_new_interpreter_stops_later_installations(
    project, tmp_path, monkeypatch
):
    root = tmp_path / "store"
    with monkeypatch.context() as context:
        context.setattr(
            operations,
            "verify_interpreter",
            lambda *a: (_ for _ in ()).throw(PluginError("installed_target_mismatch")),
        )
        result = sync(project, root)
    assert result.state == "partial" and result.exit_code == 2
    assert [p.status for p in result.plugins] == ["installed", "not_attempted"]
    assert len(list_extensions(directory=root).installations) == 1
    assert sync(project, root).exit_code == 0


def test_failed_final_probe_does_not_report_earlier_probe_as_current(
    project, tmp_path, monkeypatch
):
    root = tmp_path / "store"
    assert sync(project, root).exit_code == 0
    verify = operations.verify_interpreter
    calls = 0

    def fail_final(*args):
        nonlocal calls
        calls += 1
        if calls == 3:  # Both initial reuse probes passed; A's final probe fails.
            raise PluginError("installed_interpreter_unavailable")
        verify(*args)

    with monkeypatch.context() as context:
        context.setattr(operations, "verify_interpreter", fail_final)
        result = sync(project, root)
    assert result.state == "partial" and result.exit_code == 2
    assert not result.plugins[0].interpreter_verified
    assert len(list_extensions(directory=root).installations) == 2
    assert sync(project, root).exit_code == 0

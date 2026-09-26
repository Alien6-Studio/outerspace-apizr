"""Real installations and synchronized cross-process retirement admissions."""

import json
import selectors
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from apizr.cli import main
from apizr.extension_runtime import CleanupFailed
from apizr.local_plugins import (
    PluginError,
    activation,
    disable_extension,
    enable_extension,
    install_extension,
    list_extensions,
    retirement,
    run_extension,
    store,
    uninstall_extension,
    usage,
)
from apizr.local_plugins import uninstall as removal
from apizr.local_plugins.control import InstallControl


@pytest.fixture
def installed(wheel_factory, tmp_path):
    wheel, digest = wheel_factory()
    root = tmp_path / "plugins"
    record = install_extension(wheel, digest, directory=root)
    return root, record, wheel, digest


def tree(root):
    return {
        str(p.relative_to(root)): p.readlink() if p.is_symlink() else p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() or p.is_symlink()
    }


def line(process):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(10), "fixture did not become ready"
        return process.stdout.readline().strip()


def stop(process):
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=10)


def test_absent_preview_and_cli_preferences(tmp_path, capsys):
    root = tmp_path / "absent"
    for dry in (True, False):
        result = uninstall_extension("some-plugin", "1.0", directory=root, dry_run=dry)
        assert result.state == "absent" and result.exit_code == 0
        assert not root.exists()
    user = tmp_path / "user.toml"
    user.write_text('schema_version="apizr.user/v1"\nplugins_dir="wrong"\n')
    assert (
        main(
            [
                "plugins",
                "uninstall",
                "some-plugin",
                "--version",
                "1.0",
                "--dry-run",
                "--json",
                "--user-config",
                str(user),
                "--plugins-dir",
                str(root),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "apizr.plugin-uninstall/v1"
    assert not root.exists() and not (tmp_path / "wrong").exists()
    with pytest.raises(SystemExit):
        main(["plugins", "uninstall", "some-plugin"])


def test_remove_exact_inactive_and_repeat(installed, wheel_factory, tmp_path):
    root, old, _, _ = installed
    wheel, digest = wheel_factory(version="2.0")
    new = install_extension(wheel, digest, directory=root)
    enable_extension(new.name, new.version, directory=root)
    otherwheel, otherhash = wheel_factory(name="other")
    other = install_extension(otherwheel, otherhash, directory=root)
    other_before = tree(Path(other.python).parents[2])
    before = tree(Path(new.python).parents[2])
    snapshot = tree(root)
    preview = uninstall_extension(old.name, old.version, directory=root, dry_run=True)
    assert preview.state == "planned" and preview.target == old
    assert tree(root) == snapshot
    assert uninstall_extension(new.name, new.version, directory=root).state == "active"
    result = uninstall_extension(old.name, old.version, directory=root)
    assert result.state == "complete" and result.exit_code == 0
    assert (
        result.inventory_removed
        and result.environment_removed
        and not result.cleanup_pending
    )
    assert not Path(old.python).parents[2].exists()
    assert run_extension(new.name, "describe", {}, directory=root).result == "installed"
    assert tree(Path(new.python).parents[2]) == before
    assert tree(Path(other.python).parents[2]) == other_before
    assert uninstall_extension(old.name, old.version, directory=root).state == "absent"


@pytest.mark.parametrize("boundary", ["intent", "inventory", "files", "done"])
def test_interruption_and_exact_resume(installed, monkeypatch, boundary):
    root, record, wheel, digest = installed

    def interrupt(*a, **kw):
        raise KeyboardInterrupt

    with monkeypatch.context() as m:
        if boundary == "intent":
            m.setattr(store, "publish", interrupt)
        elif boundary == "inventory":
            m.setattr(removal, "_cleanup", interrupt)
        elif boundary == "files":
            original = removal._cleanup

            def clean(*a):
                original(*a)
                raise KeyboardInterrupt

            m.setattr(removal, "_cleanup", clean)
        else:
            original = retirement.write

            def write(root, pending):
                original(root, pending)
                if not pending:
                    raise KeyboardInterrupt

            m.setattr(retirement, "write", write)
        result = uninstall_extension(record.name, record.version, directory=root)
    assert result.state == "interrupted" and result.exit_code == 130
    assert list_extensions(directory=root).installations == []
    if boundary != "done":
        assert result.cleanup_pending
        with pytest.raises(PluginError, match="cleanup_pending"):
            enable_extension(record.name, record.version, directory=root)
        with pytest.raises(PluginError, match="cleanup_pending"):
            install_extension(wheel, digest, directory=root)
    again = uninstall_extension(record.name, record.version, directory=root)
    assert again.state == ("absent" if boundary == "done" else "complete")


def test_replaced_generation_never_deleted(installed, monkeypatch):
    root, record, _, _ = installed
    with monkeypatch.context() as m:
        m.setattr(removal, "_cleanup", lambda *a: (_ for _ in ()).throw(OSError()))
        assert (
            uninstall_extension(record.name, record.version, directory=root).state
            == "incomplete"
        )
    folder = Path(record.python).parents[2]
    moved = folder.with_name("retained")
    folder.rename(moved)
    folder.mkdir()
    (folder / "new-content").write_text("keep")
    result = uninstall_extension(record.name, record.version, directory=root)
    assert (
        result.state == "refused"
        and result.diagnostics[0].code == "removal_identity_conflict"
    )
    assert (folder / "new-content").read_text() == "keep" and moved.exists()


@pytest.mark.parametrize(
    "kind", ["environment", "parent", "inventory", "duplicate", "journal", "activation"]
)
def test_corrupt_state_and_redirects_refused(installed, tmp_path, kind):
    root, record, _, _ = installed
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_text("keep")
    if kind in ("environment", "parent"):
        folder = (
            Path(record.python).parents[2]
            if kind == "environment"
            else root / "environments"
        )
        folder.rename(tmp_path / "saved")
        folder.symlink_to(outside, target_is_directory=True)
    elif kind == "inventory":
        (root / "installations.json").write_text('{"schema":"invalid"}')
    elif kind == "duplicate":
        value = json.loads((root / "installations.json").read_text())
        value["installations"] *= 2
        (root / "installations.json").write_text(json.dumps(value))
    elif kind == "journal":
        (root / "removals.json").write_text('{"pending":[],"pending":[]}')
    else:
        (root / "activations.json").write_text('{"invalid":true}')
    assert (
        uninstall_extension(record.name, record.version, directory=root).exit_code != 0
    )
    assert (outside / "sentinel").read_text() == "keep"


def test_internal_symlinks_and_missing_interpreter(installed, tmp_path):
    root, record, _, _ = installed
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("yes")
    folder = Path(record.python).parents[2]
    (folder / "external").symlink_to(outside, target_is_directory=True)
    Path(record.python).unlink()
    assert (
        uninstall_extension(record.name, record.version, directory=root).state
        == "complete"
    )
    assert (outside / "keep").read_text() == "yes"


def test_running_call_survives_disable_and_refuses_removal(wheel_factory, tmp_path):
    # The peer announces readiness over a real socket and waits for explicit release.
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    address = listener.getsockname()[1]
    listener.listen()
    listener.settimeout(10)
    peer = b"import json,socket,sys\nr=json.load(sys.stdin)\ns=socket.socket(); s.connect(('127.0.0.1',r['arguments']['socket'])); s.sendall(b'R'); s.recv(1); s.close()\nprint(json.dumps({k:r[k] for k in ('protocol','request_id','operation')}|{'status':'ok','result':'done'}))\n"
    wheel, digest = wheel_factory(files={"local_probe.py": peer})
    root = tmp_path / "plugins"
    record = install_extension(wheel, digest, directory=root)
    enable_extension(record.name, record.version, directory=root)
    args = tmp_path / "args.json"
    args.write_text(json.dumps({"socket": address}))
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-m",
            "apizr.cli",
            "plugins",
            "run",
            record.name,
            "wait",
            "--arguments",
            str(args),
            "--plugins-dir",
            str(root),
            "--timeout-ms",
            "20000",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(10)
            assert connection.recv(1) == b"R"
            disable_extension(record.name, directory=root)
            for dry in (True, False):
                result = uninstall_extension(
                    record.name, record.version, directory=root, dry_run=dry
                )
                assert result.state == "busy" and result.exit_code == 1
            connection.sendall(b"G")
        out, err = process.communicate(timeout=10)
        assert process.returncode == 0, (out, err)
        assert json.loads(out)["result"] == "done"
        assert (
            uninstall_extension(record.name, record.version, directory=root).state
            == "complete"
        )
    finally:
        stop(process)
        listener.close()


def test_execve_keeps_lease_until_session_exit(wheel_factory, tmp_path):
    wheel, digest = wheel_factory(
        name="apizr-mcp",
        manifest_changes={"module": "apizr_mcp"},
        files={
            "apizr_mcp.py": b"import sys\nprint('ready',flush=True)\nsys.stdin.readline()\n"
        },
    )
    root = tmp_path / "plugins"
    record = install_extension(wheel, digest, directory=root)
    enable_extension(record.name, record.version, directory=root)
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-m",
            "apizr.cli",
            "mcp",
            "serve",
            "--project",
            str(tmp_path / "apizr.toml"),
            "--plugins-dir",
            str(root),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert line(process) == b"ready"
        disable_extension(record.name, directory=root)
        assert (
            uninstall_extension(record.name, record.version, directory=root).state
            == "busy"
        )
        process.communicate(b"close\n", timeout=10)
        assert process.returncode == 0
        assert (
            uninstall_extension(record.name, record.version, directory=root).state
            == "complete"
        )
    finally:
        stop(process)


def test_cancel_deadline_and_entry_bound(installed, monkeypatch):
    root, record, _, _ = installed
    event = threading.Event()
    event.set()
    assert (
        uninstall_extension(
            record.name, record.version, directory=root, cancel=event
        ).state
        == "interrupted"
    )
    with monkeypatch.context() as m:
        m.setattr(removal, "MAX_ENTRIES", 1)
        result = uninstall_extension(record.name, record.version, directory=root)
    assert result.state == "incomplete" and result.cleanup_pending
    assert (
        uninstall_extension(record.name, record.version, directory=root).state
        == "complete"
    )
    assert (
        uninstall_extension(
            record.name, record.version, directory=root, timeout_ms=0
        ).exit_code
        == 2
    )


def test_store_lock_wait_is_bounded(installed):
    root, record, _, _ = installed
    with store.installation_lock(root):
        start = time.monotonic()
        result = uninstall_extension(
            record.name, record.version, directory=root, timeout_ms=30
        )
        assert time.monotonic() - start < 1
        assert result.diagnostics[0].code == "uninstall_timeout"
    assert (
        uninstall_extension(record.name, record.version, directory=root).state
        == "complete"
    )


def test_uncertain_runtime_cleanup_blocks_uninstall(installed, monkeypatch):
    root, record, _, _ = installed
    enable_extension(record.name, record.version, directory=root)

    def fail(*a, **k):
        raise CleanupFailed()

    monkeypatch.setattr(activation, "invoke_extension", fail)
    with pytest.raises(CleanupFailed):
        run_extension(record.name, "test", {}, directory=root)
    disable_extension(record.name, directory=root)
    assert (
        uninstall_extension(record.name, record.version, directory=root).state
        == "unconfirmed"
    )


def test_interpreter_probe_lease_excludes_delete(installed):
    root, record, _, _ = installed
    with usage.protect(record, root, InstallControl(time.monotonic() + 10)):
        assert (
            uninstall_extension(record.name, record.version, directory=root).state
            == "busy"
        )
    assert (
        uninstall_extension(record.name, record.version, directory=root).state
        == "complete"
    )
    with pytest.raises(PluginError, match="installation_changed"):
        with usage.protect(record, root):
            pass


@pytest.mark.parametrize("operation", ["enable", "install"])
def test_removal_serializes_concurrent_mutations(installed, monkeypatch, operation):
    from concurrent.futures import ThreadPoolExecutor

    root, record, wheel, digest = installed
    entered, release, contender = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    original = removal._cleanup

    def cleanup(*args):
        entered.set()
        assert release.wait(10)
        original(*args)

    def mutate():
        contender.set()
        if operation == "enable":
            with pytest.raises(PluginError, match="not_installed"):
                enable_extension(record.name, record.version, directory=root)
        else:
            return install_extension(wheel, digest, directory=root)

    monkeypatch.setattr(removal, "_cleanup", cleanup)
    with ThreadPoolExecutor(2) as executor:
        removing = executor.submit(
            uninstall_extension, record.name, record.version, directory=root
        )
        try:
            assert entered.wait(10)
            change = executor.submit(mutate)
            assert contender.wait(10)
            assert not change.done()
        finally:
            release.set()
        assert removing.result(timeout=10).state == "complete"
        fresh = change.result(timeout=10)
    if operation == "install":
        assert fresh.environment_id != record.environment_id
        assert Path(fresh.python).is_file()
        enable_extension(fresh.name, fresh.version, directory=root)
        assert (
            run_extension(fresh.name, "describe", {}, directory=root).result
            == "installed"
        )


@pytest.mark.parametrize(
    "kind", ["too-large", "fifo", "duplicate", "wrong-python", "duplicate-identity"]
)
def test_invalid_retirement_records(installed, kind):
    root, record, _, _ = installed
    path = root / "removals.json"
    info = Path(record.python).parents[2].stat()
    retirement.write(
        root,
        [
            retirement.Retirement(
                installation=record, device=info.st_dev, inode=info.st_ino
            )
        ],
    )
    if kind == "too-large":
        path.write_bytes(b" " * (1024 * 1024 + 1))
    elif kind == "fifo":
        import os

        path.unlink()
        os.mkfifo(path)
    elif kind == "duplicate":
        path.write_text('{"pending":[],"pending":[]}')
    else:
        value = json.loads(path.read_text())
        if kind == "wrong-python":
            value["pending"][0]["installation"]["python"] = "/outside"
        else:
            value["pending"] *= 2
        path.write_text(json.dumps(value))
    result = uninstall_extension(record.name, record.version, directory=root)
    assert (
        result.exit_code == 2 and result.diagnostics[0].code == "invalid_removal_state"
    )
    assert Path(record.python).is_file()


def test_pending_conflict_never_removes_new_record(installed, monkeypatch):
    root, record, _, _ = installed
    with monkeypatch.context() as m:
        m.setattr(removal, "_cleanup", lambda *a: (_ for _ in ()).throw(OSError()))
        assert uninstall_extension(
            record.name, record.version, directory=root
        ).cleanup_pending
    other = record.model_copy(
        update={
            "environment_id": "b" * 32,
            "python": str(root / "environments" / ("b" * 32) / "venv/bin/python"),
        }
    )
    store.publish(root, store.Inventory(installations=[other]))
    result = uninstall_extension(record.name, record.version, directory=root)
    assert result.diagnostics[0].code == "removal_identity_conflict"
    assert Path(record.python).is_file()


@pytest.mark.parametrize("kind", ["symlink", "fifo", "writable"])
def test_unsafe_usage_lock_refused(installed, kind, tmp_path):
    import os

    root, record, _, _ = installed
    enable_extension(record.name, record.version, directory=root)
    assert (
        run_extension(record.name, "describe", {}, directory=root).result == "installed"
    )
    disable_extension(record.name, directory=root)
    lock = root / ".usage" / f"{record.environment_id}.lock"
    lock.unlink()
    if kind == "symlink":
        lock.symlink_to(tmp_path / "other")
    elif kind == "fifo":
        os.mkfifo(lock)
    else:
        lock.write_bytes(b"")
        lock.chmod(0o666)
    assert (
        uninstall_extension(record.name, record.version, directory=root).exit_code == 2
    )
    assert Path(record.python).is_file()


def test_cleanup_deadline_cancellation_and_unconfirmed_observation(
    installed, monkeypatch
):
    root, record, _, _ = installed
    cancelled = threading.Event()
    with monkeypatch.context() as m:

        def cleanup(root, item, control):
            cancelled.set()
            control.check()

        m.setattr(removal, "_cleanup", cleanup)
        result = uninstall_extension(
            record.name, record.version, directory=root, cancel=cancelled
        )
        assert result.state == "interrupted" and result.cleanup_pending
    with monkeypatch.context() as m:

        def fail(root, item, control):
            (root / "removals.json").write_text("invalid")
            raise OSError

        m.setattr(removal, "_cleanup", fail)
        result = uninstall_extension(record.name, record.version, directory=root)
        assert result.state == "unconfirmed" and result.exit_code == 2


def test_missing_generation_and_depth_limit(installed, monkeypatch):
    root, record, _, _ = installed
    folder = Path(record.python).parents[2]
    deep = folder / "deep" / "nested"
    deep.mkdir(parents=True)
    (deep / "data").write_text("data")
    with monkeypatch.context() as m:
        m.setattr(removal, "MAX_DEPTH", 0)
        result = uninstall_extension(record.name, record.version, directory=root)
        assert result.state == "incomplete"
    assert (
        uninstall_extension(record.name, record.version, directory=root).state
        == "complete"
    )
    store.publish(root, store.Inventory(installations=[record]))
    result = uninstall_extension(record.name, record.version, directory=root)
    assert result.diagnostics[0].code == "plugin_environment_missing"


def test_probe_cleanup_failure_guard(installed):
    root, record, _, _ = installed
    with pytest.raises(CleanupFailed):
        with usage.protect(record, root):
            raise CleanupFailed()
    assert (
        uninstall_extension(record.name, record.version, directory=root).state
        == "unconfirmed"
    )


def test_empty_existing_store_remains_unmodified(tmp_path):
    root = tmp_path / "store"
    root.mkdir(mode=0o700)
    for dry in (True, False):
        assert (
            uninstall_extension("absent", "1", directory=root, dry_run=dry).state
            == "absent"
        )
        assert list(root.iterdir()) == []

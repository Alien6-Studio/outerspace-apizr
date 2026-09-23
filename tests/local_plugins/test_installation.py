"""Real wheels and uv environments, with bounded subprocesses and crash cases."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from apizr.cli import main
from apizr.extension_runtime import Limits, invoke_extension
from apizr.local_plugins import (
    PluginError,
    backend,
    install_extension,
    list_extensions,
    store,
)

pytestmark = pytest.mark.timeout(25)


def test_real_install_list_and_explicit_invocation(
    wheel_factory, tmp_path, capsys, monkeypatch
):
    wheel, digest = wheel_factory()
    root = tmp_path / "plugins"
    before_env, before_path = dict(os.environ), list(sys.path)
    # Neither the core nor uv may inherit package-index or installation settings.
    monkeypatch.setenv("UV_INDEX_URL", "https://invalid.invalid")
    monkeypatch.setenv("UV_TARGET", str(tmp_path / "must-not-exist"))
    monkeypatch.setenv("UV_VENV_SEED", "true")
    monkeypatch.setenv("UV_COMPILE_BYTECODE", "true")
    monkeypatch.setenv("PIP_TARGET", str(tmp_path / "must-not-exist"))
    record = install_extension(wheel, digest.upper(), directory=root)
    assert record.sha256 == digest
    assert str(Path(sys.prefix)) not in record.python
    assert list_extensions(directory=root).installations == [record]
    assert main(["plugins", "list", "--plugins-dir", str(root), "--json"]) == 0
    assert (
        json.loads(capsys.readouterr().out)["installations"][0]["python"]
        == record.python
    )
    assert main(["plugins", "list", "--plugins-dir", str(root)]) == 0
    assert "local-probe 1.0" in capsys.readouterr().out
    assert (
        main(
            [
                "plugins",
                "install",
                str(wheel),
                "--sha256",
                digest,
                "--plugins-dir",
                str(root),
            ]
        )
        == 0
    )
    assert "Installed local-probe 1.0" in capsys.readouterr().out
    assert not (tmp_path / "must-not-exist").exists()
    assert (
        invoke_extension(
            record.python,
            record.module,
            "describe",
            {},
            limits=Limits(),
            environment={},
        ).result
        == "installed"
    )
    inventory = subprocess.check_output(
        [
            record.python,
            "-I",
            "-B",
            "-c",
            "from importlib.metadata import distributions; print(sorted(d.metadata['Name'] for d in distributions()))",
        ],
        timeout=5,
        text=True,
    )
    assert inventory.strip() == "['local-probe']"
    assert "local_probe" not in sys.modules and sys.path == before_path
    assert all(
        os.environ[key] == value
        for key, value in before_env.items()
        if not key.startswith(("UV_", "PIP_"))
    )


def test_no_import_or_execution_during_install(wheel_factory, tmp_path):
    marker = tmp_path / "executed"
    wheel, digest = wheel_factory(
        files={
            "local_probe.py": f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('must not run')\n".encode()
        }
    )
    record = install_extension(wheel, digest, directory=tmp_path / "plugins")
    assert record.name == "local-probe" and not marker.exists()


def test_list_empty_is_read_only_without_uv(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: pytest.fail("no subprocess")
    )
    root = tmp_path / "absent"
    assert main(["plugins", "list", "--plugins-dir", str(root)]) == 0
    assert capsys.readouterr().out == "No local extensions installed.\n"
    assert list_extensions(directory=root).installations == []
    assert not root.exists()


def test_missing_uv_before_any_modification(wheel_factory, tmp_path, monkeypatch):
    wheel, digest = wheel_factory()
    root = tmp_path / "absent"
    monkeypatch.setenv("PATH", "")
    with pytest.raises(PluginError, match="uv_not_found"):
        install_extension(wheel, digest, directory=root)
    assert not root.exists()


@pytest.mark.parametrize(
    "python", [Path("relative"), Path("/nonexistent/apizr-python")]
)
def test_missing_interpreter(wheel_factory, tmp_path, python):
    wheel, digest = wheel_factory()
    with pytest.raises(PluginError, match="python_unavailable"):
        install_extension(wheel, digest, directory=tmp_path / "plugins", python=python)
    assert not (tmp_path / "plugins").exists()


def test_reinstall_conflict_preserves_original(wheel_factory, tmp_path, monkeypatch):
    wheel, digest = wheel_factory()
    root = tmp_path / "plugins"
    installed = install_extension(wheel, digest, directory=root)
    before = (root / "installations.json").read_bytes()
    original = wheel.read_bytes()
    with monkeypatch.context() as context:
        context.setattr(backend, "run_uv", lambda *a: pytest.fail("idempotent"))
        assert install_extension(wheel, digest, directory=root) == installed
    wheel, changed = wheel_factory(files={"extra.txt": b"different"})
    with pytest.raises(PluginError, match="installation_conflict"):
        install_extension(wheel, changed, directory=root)
    assert (root / "installations.json").read_bytes() == before
    assert (
        invoke_extension(
            installed.python,
            installed.module,
            "describe",
            {},
            limits=Limits(),
            environment={},
        ).result
        == "installed"
    )
    Path(installed.python).unlink()
    with pytest.raises(PluginError, match="installed_python_unavailable"):
        wheel.write_bytes(original)
        install_extension(wheel, digest, directory=root)


def test_verified_snapshot_survives_source_replacement(
    wheel_factory, tmp_path, monkeypatch
):
    wheel, digest = wheel_factory()
    run = backend.run_uv

    def replace_source(*args):
        wheel.write_bytes(b"replaced after validation")
        run(*args)

    monkeypatch.setattr(backend, "run_uv", replace_source)
    installed = install_extension(wheel, digest, directory=tmp_path / "plugins")
    assert installed.sha256 == digest


def test_uv_rechecks_snapshot_hash(wheel_factory, tmp_path, monkeypatch):
    wheel, digest = wheel_factory()
    run = backend.run_uv

    def tamper(executable, arguments, work):
        if arguments[0] == "pip":
            with (work / wheel.name).open("ab") as output:
                output.write(b"changed after preflight")
        run(executable, arguments, work)

    monkeypatch.setattr(backend, "run_uv", tamper)
    root = tmp_path / "plugins"
    with pytest.raises(PluginError, match="uv_install_failed"):
        install_extension(wheel, digest, directory=root)
    assert list_extensions(directory=root).installations == []
    assert not list((root / "environments").iterdir())


@pytest.mark.parametrize("failure", [KeyboardInterrupt, OSError])
def test_interruption_or_failure_preserves_existing(
    wheel_factory, tmp_path, monkeypatch, failure
):
    wheel, digest = wheel_factory()
    root = tmp_path / "plugins"
    old = install_extension(wheel, digest, directory=root)
    wheel, digest = wheel_factory(version="2.0")
    run = backend.run_uv

    def interrupt(executable, arguments, work):
        if arguments[0] == "pip":
            raise failure()
        run(executable, arguments, work)

    with monkeypatch.context() as context:
        context.setattr(backend, "run_uv", interrupt)
        with pytest.raises((KeyboardInterrupt, PluginError)):
            install_extension(wheel, digest, directory=root)
    assert list_extensions(directory=root).installations == [old]
    assert len(list((root / "environments").iterdir())) == 1
    assert install_extension(wheel, digest, directory=root).version == "2.0"


def test_interrupt_immediately_after_commit_keeps_available_environment(
    wheel_factory, tmp_path, monkeypatch
):
    wheel, digest = wheel_factory()
    publish = store.publish

    def interrupt(*args):
        publish(*args)
        raise KeyboardInterrupt()

    monkeypatch.setattr(store, "publish", interrupt)
    root = tmp_path / "plugins"
    with pytest.raises(KeyboardInterrupt):
        install_extension(wheel, digest, directory=root)
    record = list_extensions(directory=root).installations[0]
    assert Path(record.python).is_file()


def child_install(wheel, digest, root, *, env=None):
    return subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-m",
            "apizr.cli",
            "plugins",
            "install",
            str(wheel),
            "--sha256",
            digest,
            "--plugins-dir",
            str(root),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def test_concurrent_processes_do_not_lose_records(wheel_factory, tmp_path):
    one, h1 = wheel_factory()
    two, h2 = wheel_factory(name="second-probe")
    root = tmp_path / "plugins"
    processes = [
        child_install(one, h1, root),
        child_install(two, h2, root),
        child_install(one, h1, root),
    ]
    try:
        for process in processes:
            out, err = process.communicate(timeout=15)
            assert process.returncode == 0, (out, err)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
    assert len(list_extensions(directory=root).installations) == 2
    assert len(list((root / "environments").iterdir())) == 2


@pytest.mark.parametrize("interrupt", [signal.SIGINT, signal.SIGKILL])
def test_interrupted_real_subprocess_never_publishes(
    wheel_factory, tmp_path, interrupt
):
    wheel, digest = wheel_factory()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "backend-pid"
    wrapper = bin_dir / "uv"
    wrapper.write_text(
        f"#!{sys.executable}\nimport os,time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n"
    )
    wrapper.chmod(0o700)
    root = tmp_path / "plugins"
    process = child_install(
        wheel, digest, root, env={**os.environ, "PATH": str(bin_dir)}
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        process.send_signal(interrupt)
        out, err = process.communicate(timeout=5)
        assert process.returncode == (
            130 if interrupt == signal.SIGINT else -signal.SIGKILL
        ), (out, err)
        if interrupt == signal.SIGINT:
            with pytest.raises(ProcessLookupError):
                os.kill(int(marker.read_text()), 0)
        assert list_extensions(directory=root).installations == []
        if interrupt == signal.SIGINT:
            assert not list((root / "environments").iterdir())
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)
        if marker.exists():
            try:
                os.killpg(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
    assert install_extension(wheel, digest, directory=root).name == "local-probe"


def test_concurrent_conflicting_content_has_one_winner(wheel_factory, tmp_path):
    import shutil

    wheel, digest = wheel_factory()
    copy = tmp_path / "copy"
    copy.mkdir()
    old_wheel = copy / wheel.name
    shutil.copyfile(wheel, old_wheel)
    wheel, changed = wheel_factory(files={"extra.txt": b"different bytes"})
    root = tmp_path / "plugins"
    processes = [
        child_install(old_wheel, digest, root),
        child_install(wheel, changed, root),
    ]
    try:
        outputs = [process.communicate(timeout=15) for process in processes]
        assert sorted(process.returncode for process in processes) == [0, 2], outputs
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
    records = list_extensions(directory=root).installations
    assert len(records) == 1 and records[0].sha256 in (digest, changed)
    assert len(list((root / "environments").iterdir())) == 1


def test_cli_failures_and_interruption(wheel_factory, tmp_path, capsys, monkeypatch):
    wheel, digest = wheel_factory()
    args = [
        "plugins",
        "install",
        str(wheel),
        "--sha256",
        digest,
        "--plugins-dir",
        str(tmp_path / "plugins"),
    ]
    import apizr.plugins_cli as cli

    monkeypatch.setattr(
        cli,
        "install_from_source",
        lambda *a, **k: (_ for _ in ()).throw(PluginError("uv_not_found")),
    )
    assert main(args) == 2 and "uv_not_found" in capsys.readouterr().err
    monkeypatch.setattr(
        cli,
        "install_from_source",
        lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    assert main(args) == 130 and "interrupted" in capsys.readouterr().err

"""Explicit activation, exact records and invocation through the existing runtime."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest

from apizr.cli import main
from apizr.extension_runtime import (
    InvalidInvocation,
    InvocationCancelled,
    InvocationTimeout,
    Limits,
    PluginFailed,
    PrerequisiteMissing,
    SizeLimitExceeded,
)
from apizr.local_plugins import (
    PluginError,
    activation,
    disable_extension,
    enable_extension,
    install_extension,
    list_extensions,
    read_arguments,
    run_extension,
    store,
)

pytestmark = pytest.mark.timeout(25)


@pytest.fixture
def installed(wheel_factory, tmp_path):
    peer = Path(__file__).with_name("activation_peer.py").read_bytes()
    wheel, digest = wheel_factory(files={"local_probe.py": peer})
    root = tmp_path / "plugins"
    record = install_extension(wheel, digest, directory=root)
    return root, record


def test_full_cli_lifecycle(installed, tmp_path, capsys, monkeypatch):
    root, record = installed
    argument_file = tmp_path / "arguments.json"
    argument_file.write_text('{"value":"explicit"}')

    def cli(*args):
        code = main(["plugins", *args, "--plugins-dir", str(root)])
        output = capsys.readouterr()
        return code, output

    assert not (root / "activations.json").exists()
    code, out = cli("run", record.name, "describe", "--arguments", str(argument_file))
    assert code == 2 and out.out == "" and "plugin_inactive" in out.err
    before = (root / "installations.json").read_bytes()
    with monkeypatch.context() as context:
        context.setattr(
            subprocess,
            "Popen",
            lambda *a, **k: pytest.fail("activation cannot launch anything"),
        )
        context.setenv("PATH", "")
        assert cli("enable", "LOCAL_Probe", "--version", record.version)[0] == 0
        assert json.loads(cli("list", "--active", "--json")[1].out) == json.loads(
            cli("list", "--json")[1].out
        )
    monkeypatch.setenv("APIZR_PARENT_SECRET", "not-for-plugin")
    code, out = cli("run", record.name, "describe", "--arguments", str(argument_file))
    assert code == 0 and out.err == ""
    response = json.loads(out.out)
    assert (
        response["protocol"] == record.protocol and response["operation"] == "describe"
    )
    assert response["result"]["value"] == "explicit"
    assert "APIZR_PARENT_SECRET" not in response["result"]["environment"]
    assert cli("disable", record.name)[0] == 0
    assert json.loads(cli("list", "--active", "--json")[1].out)["installations"] == []
    assert (
        cli("run", record.name, "describe", "--arguments", str(argument_file))[0] == 2
    )
    assert (root / "installations.json").read_bytes() == before


def test_idempotence_exact_version_and_no_implicit_switch(installed, wheel_factory):
    root, record = installed
    enable_extension(record.name, record.version, directory=root)
    path = root / "activations.json"
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    assert enable_extension(record.name, record.version, directory=root) == record
    assert path.read_bytes() == before and path.stat().st_mtime_ns == mtime
    wheel, digest = wheel_factory(version="2.0")
    second = install_extension(wheel, digest, directory=root)
    assert path.read_bytes() == before
    assert list_extensions(directory=root, active=True).installations == [record]
    with pytest.raises(PluginError, match="plugin_not_installed"):
        enable_extension(record.name, "3.0", directory=root)
    assert path.read_bytes() == before
    enable_extension(record.name, second.version, directory=root)
    assert list_extensions(directory=root, active=True).installations == [second]
    disable_extension(record.name, directory=root)
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    disable_extension(record.name, directory=root)
    assert path.read_bytes() == before and path.stat().st_mtime_ns == mtime


def test_absent_operations_do_not_create_storage(tmp_path):
    root = tmp_path / "absent"
    disable_extension("local-probe", directory=root)
    assert list_extensions(directory=root, active=True).installations == []
    for call in (
        lambda: enable_extension("local-probe", "1.0", directory=root),
        lambda: run_extension("local-probe", "describe", {}, directory=root),
    ):
        with pytest.raises(PluginError, match="plugin_not_installed"):
            call()
    assert not root.exists()
    with pytest.raises(PluginError, match="invalid_plugin_name"):
        disable_extension("../bad", directory=root)


@pytest.mark.parametrize(
    "changed", ["sha256", "environment_id", "version", "module", "python"]
)
def test_activation_is_bound_to_entire_record(installed, changed):
    root, record = installed
    enable_extension(record.name, record.version, directory=root)
    path = root / "activations.json"
    state = json.loads(path.read_text())
    state["activations"][0][changed] = {
        "sha256": "0" * 64,
        "environment_id": "0" * 32,
        "version": "9.0",
        "module": "other",
        "python": sys.executable,
    }[changed]
    path.write_text(json.dumps(state))
    with pytest.raises(PluginError, match="activation_mismatch"):
        run_extension(record.name, "describe", {}, directory=root)
    with pytest.raises(PluginError, match="activation_mismatch"):
        list_extensions(directory=root, active=True)
    # A stale but structurally valid selection can still be explicitly disabled.
    disable_extension(record.name, directory=root)
    assert list_extensions(directory=root, active=True).installations == []


@pytest.mark.parametrize(
    "payload",
    [
        "garbage",
        '{"schema":"x","schema":"y"}',
        '{"schema":"apizr.active-extensions/v99","activations":[]}',
        '{"schema":"apizr.active-extensions/v1","activations":[],"unknown":true}',
    ],
)
def test_corrupt_activation_fails_closed(installed, payload):
    root, record = installed
    (root / "activations.json").write_text(payload)
    for call in (
        lambda: enable_extension(record.name, record.version, directory=root),
        lambda: disable_extension(record.name, directory=root),
        lambda: list_extensions(directory=root, active=True),
        lambda: run_extension(record.name, "describe", {}, directory=root),
    ):
        with pytest.raises(PluginError, match="invalid_activation"):
            call()
    assert list_extensions(directory=root).installations == [record]


def test_duplicate_oversized_special_and_symlink_activation(
    installed, monkeypatch, tmp_path
):
    root, record = installed
    enable_extension(record.name, record.version, directory=root)
    path = root / "activations.json"
    state = json.loads(path.read_text())
    state["activations"] *= 2
    path.write_text(json.dumps(state))
    with pytest.raises(PluginError, match="invalid_activation"):
        run_extension(record.name, "describe", {}, directory=root)
    with monkeypatch.context() as context:
        context.setattr(store, "MAX_INVENTORY_BYTES", 10)
        with pytest.raises(PluginError, match="invalid_activation"):
            activation._read(root)
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(PluginError, match="invalid_activation"):
        activation._read(root)
    path.unlink()
    path.symlink_to(tmp_path / "elsewhere")
    with pytest.raises(PluginError, match="activation_unavailable"):
        run_extension(record.name, "describe", {}, directory=root)


def test_missing_interpreter_and_redirected_environment(installed, tmp_path):
    root, record = installed
    enable_extension(record.name, record.version, directory=root)
    python = Path(record.python)
    python.unlink()
    with pytest.raises(PrerequisiteMissing):
        run_extension(record.name, "describe", {}, directory=root)
    with pytest.raises(PrerequisiteMissing):
        enable_extension(record.name, record.version, directory=root)
    assert list_extensions(directory=root, active=True).installations == [record]
    # A venv directory cannot redirect the recorded location into another tree.
    old = python.parent
    moved = tmp_path / "elsewhere"
    old.rename(moved)
    old.symlink_to(moved, target_is_directory=True)
    with pytest.raises(PluginError, match="invalid_inventory"):
        run_extension(record.name, "describe", {}, directory=root)


@pytest.mark.parametrize(
    "payload",
    [
        b"[]",
        b"null",
        b'{"a":1,"a":2}',
        b'{"x":{"a":1,"a":2}}',
        b'{"x":NaN}',
        b"{} {}",
        b"\xff",
    ],
)
def test_invalid_argument_objects(tmp_path, payload):
    path = tmp_path / "arguments.json"
    path.write_bytes(payload)
    with pytest.raises(InvalidInvocation):
        read_arguments(path)


def test_bounded_regular_argument_files(tmp_path):
    path = tmp_path / "args"
    path.write_text('{"value":1}')
    assert read_arguments(path) == {"value": 1}
    with pytest.raises(SizeLimitExceeded) as error:
        read_arguments(path, limits=Limits(max_request_bytes=5))
    assert error.value.stream == "request"
    with pytest.raises(InvalidInvocation):
        read_arguments(path, limits=Limits.model_construct(max_request_bytes=-1))
    path.unlink()
    with pytest.raises(PluginError, match="arguments_unavailable"):
        read_arguments(path)
    os.mkfifo(path)
    with pytest.raises(InvalidInvocation):
        read_arguments(path)


def test_atomic_activation_failure_preserves_old_selection(
    installed, wheel_factory, monkeypatch
):
    root, record = installed
    enable_extension(record.name, record.version, directory=root)
    wheel, digest = wheel_factory(version="2.0")
    install_extension(wheel, digest, directory=root)
    before = (root / "activations.json").read_bytes()
    with monkeypatch.context() as context:
        context.setattr(
            store.os, "replace", Mock(side_effect=OSError("sensitive path"))
        )
        with pytest.raises(PluginError, match="activation_unavailable"):
            enable_extension(record.name, "2.0", directory=root)
        with pytest.raises(PluginError, match="activation_unavailable"):
            disable_extension(record.name, directory=root)
    assert (root / "activations.json").read_bytes() == before
    assert list_extensions(directory=root, active=True).installations == [record]


def test_full_activation_store_is_refused_without_leaking_records(installed):
    root, record = installed
    path = root / "activations.json"
    state = {
        "schema": "apizr.active-extensions/v1",
        "activations": [
            {**record.model_dump(by_alias=True), "name": f"stale-{index}"}
            for index in range(1000)
        ],
    }
    path.write_text(json.dumps(state))
    before = path.read_bytes()
    with pytest.raises(PluginError) as error:
        enable_extension(record.name, record.version, directory=root)
    assert str(error.value) == "activation_full"
    assert path.read_bytes() == before


def wait_marker(marker):
    end = time.monotonic() + 5
    while not marker.exists() and time.monotonic() < end:
        time.sleep(0.01)
    assert marker.exists()


def test_disable_does_not_interrupt_admitted_call(installed, tmp_path):
    root, record = installed
    enable_extension(record.name, record.version, directory=root)
    marker = tmp_path / "pid"
    with ThreadPoolExecutor() as pool:
        call = pool.submit(
            run_extension,
            record.name,
            "describe",
            {"marker": str(marker), "wait": 0.7},
            directory=root,
            limits=Limits(wall_time_ms=3000),
        )
        wait_marker(marker)
        disable_extension(record.name, directory=root)
        with pytest.raises(PluginError, match="plugin_inactive"):
            run_extension(record.name, "describe", {}, directory=root)
        assert call.result(timeout=5).status == "ok"


def test_runtime_errors_cancellation_and_recovery(installed, tmp_path):
    root, record = installed
    enable_extension(record.name, record.version, directory=root)
    with pytest.raises(PluginFailed):
        run_extension(record.name, "describe", {"fail": True}, directory=root)
    with pytest.raises(InvocationTimeout):
        run_extension(
            record.name,
            "describe",
            {"wait": 30},
            directory=root,
            limits=Limits(wall_time_ms=300),
        )
    cancel = threading.Event()
    marker = tmp_path / "pid"
    with ThreadPoolExecutor() as pool:
        call = pool.submit(
            run_extension,
            record.name,
            "describe",
            {"marker": str(marker), "wait": 30},
            directory=root,
            cancel=cancel,
        )
        try:
            wait_marker(marker)
        finally:
            cancel.set()
        with pytest.raises(InvocationCancelled):
            call.result(timeout=5)
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)
    assert run_extension(record.name, "describe", {}, directory=root).status == "ok"


def test_cli_interrupt_is_redacted_and_reaps(installed, tmp_path):
    root, record = installed
    enable_extension(record.name, record.version, directory=root)
    marker = tmp_path / "pid"
    arguments = tmp_path / "args.json"
    arguments.write_text(
        json.dumps({"marker": str(marker), "wait": 30, "value": "ARGUMENT-SENTINEL"})
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-m",
            "apizr.cli",
            "plugins",
            "run",
            record.name,
            "describe",
            "--arguments",
            str(arguments),
            "--plugins-dir",
            str(root),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_marker(marker)
        process.send_signal(signal.SIGINT)
        out, err = process.communicate(timeout=5)
        assert (
            process.returncode == 130
            and out == b""
            and err == b"apizr plugins: cancelled\n"
        )
        assert b"ARGUMENT-SENTINEL" not in err
        with pytest.raises(ProcessLookupError):
            os.kill(int(marker.read_text()), 0)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)
        if marker.exists():
            try:
                os.kill(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
    assert run_extension(record.name, "describe", {}, directory=root).status == "ok"


def test_concurrent_activations_and_install_preserve_records(installed, wheel_factory):
    root, record = installed
    wheel, digest = wheel_factory(name="second-probe")
    second = install_extension(wheel, digest, directory=root)
    wheel, digest = wheel_factory(version="2.0")
    calls = []
    try:
        for selected in (record, second):
            calls.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        "-m",
                        "apizr.cli",
                        "plugins",
                        "enable",
                        selected.name,
                        "--version",
                        selected.version,
                        "--plugins-dir",
                        str(root),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            )
        install_extension(wheel, digest, directory=root)
        for call in calls:
            out, err = call.communicate(timeout=10)
            assert call.returncode == 0, (out, err)
    finally:
        for call in calls:
            if call.poll() is None:
                call.kill()
            call.wait(timeout=3)
    assert list_extensions(directory=root, active=True).installations == [
        record,
        second,
    ]
    assert len(list_extensions(directory=root).installations) == 3

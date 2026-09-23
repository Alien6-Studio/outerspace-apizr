"""Bounded real processes, recovery after errors, and redacted diagnostics."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from unittest.mock import Mock

import pytest
from execution.observation import wait_for_terminal_process

from apizr.extension_runtime import (
    CleanupFailed,
    InvalidInvocation,
    InvocationCancelled,
    InvocationTimeout,
    Limits,
    PluginFailed,
    PrerequisiteMissing,
    ProtocolInvalid,
    SizeLimitExceeded,
    invoke_extension,
    supervisor,
)

pytestmark = pytest.mark.timeout(20)


def invoke(python, arguments=None, **options):
    return invoke_extension(
        python,
        "invocation_fixture",
        "describe",
        arguments or {},
        limits=options.pop("limits", Limits(wall_time_ms=3000)),
        environment=options.pop("environment", {}),
        **options,
    )


def recover(python):
    result = invoke(python)
    assert result.result == "ok"
    return result


def test_fresh_process_correlated_reply_and_explicit_environment(
    extension_python, monkeypatch, capfd
):
    monkeypatch.setenv("APIZR_PARENT_SECRET", "not-for-the-plugin")
    before, paths = dict(os.environ), list(sys.path)
    replies = [
        invoke(
            extension_python,
            {"mode": "inspect", "secret": "stdin-only"},
            environment={"VISIBLE": "explicit"},
        )
        for _ in range(2)
    ]
    assert replies[0].request_id != replies[1].request_id
    assert all(reply.operation == "describe" for reply in replies)
    for reply in replies:
        assert reply.result["arguments"]["secret"] == "stdin-only"
        assert reply.result["env"]["VISIBLE"] == "explicit"
        assert "APIZR_PARENT_SECRET" not in reply.result["env"]
        assert "stdin-only" not in str(reply.result["argv"])
        assert not Path(reply.result["cwd"]).exists()
        assert reply.result["pid"] != os.getpid()
    assert replies[0].result["cwd"] != replies[1].result["cwd"]
    assert dict(os.environ) == before and sys.path == paths
    assert "invocation_fixture" not in sys.modules
    assert capfd.readouterr() == ("", "")


@pytest.mark.parametrize(
    "arguments",
    [
        {"mode": "change", "change": {"protocol": "apizr.extension/v2"}},
        {"mode": "change", "change": {"request_id": "0" * 32}},
        {"mode": "change", "change": {"operation": "other"}},
        {"mode": "change", "change": {"extra": True}},
        {"mode": "change", "change": {"status": "unknown"}},
        {"mode": "change", "change": {"error": {"code": "x", "message": "private"}}},
        {"mode": "raw", "raw": "not JSON secret"},
        {"mode": "raw", "raw": "{}\n{}"},
        {"mode": "raw", "raw": '{"result":1,"result":2}'},
        {"mode": "raw", "raw": '{"result":NaN}'},
        {"mode": "utf8"},
    ],
)
def test_invalid_protocol_then_recovery(extension_python, arguments):
    with pytest.raises(ProtocolInvalid) as caught:
        invoke(extension_python, arguments)
    assert str(caught.value) == "protocol_invalid"
    recover(extension_python)


@pytest.mark.parametrize("mode", ["fail", "error"])
def test_plugin_failure_redacted_then_recovery(extension_python, mode):
    secret = "VERY-SENSITIVE-VALUE"
    with pytest.raises(PluginFailed) as caught:
        invoke(extension_python, {"mode": mode, "secret": secret})
    assert secret not in "".join(traceback.format_exception(caught.value))
    assert secret not in repr(caught.value)
    assert "PLUGIN-DIAGNOSTIC-SENTINEL" not in "".join(
        traceback.format_exception(caught.value)
    )
    assert "PLUGIN-DIAGNOSTIC-SENTINEL" not in repr(caught.value)
    recover(extension_python)


@pytest.mark.parametrize("which", ["missing", "relative", "not-executable"])
def test_missing_prerequisite_then_recovery(extension_python, tmp_path, which):
    python = {
        "missing": tmp_path / "missing",
        "relative": Path("python"),
        "not-executable": tmp_path / "file",
    }[which]
    if which == "not-executable":
        python.write_text("not executable")
        python.chmod(0o600)
    with pytest.raises(PrerequisiteMissing):
        invoke(python)
    recover(extension_python)


def test_missing_module_is_plugin_failure(extension_python):
    with pytest.raises(PluginFailed):
        invoke_extension(
            extension_python,
            "absent_extension",
            "describe",
            {},
            limits=Limits(),
            environment={},
        )
    recover(extension_python)


@pytest.mark.parametrize(
    "stream,continuous",
    [("stdout", False), ("stderr", False), ("stdout", True), ("stderr", True)],
)
def test_output_limits_during_read_and_cleanup(
    extension_python, tmp_path, monkeypatch, stream, continuous
):
    processes = []
    popen = supervisor.subprocess.Popen

    def record(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(supervisor.subprocess, "Popen", record)
    marker = tmp_path / "pid"
    with pytest.raises(SizeLimitExceeded) as caught:
        invoke(
            extension_python,
            {
                "mode": stream,
                "count": 8192,
                "continuous": continuous,
                "marker": str(marker),
            },
            limits=Limits(max_stdout_bytes=512, max_stderr_bytes=512),
        )
    assert caught.value.stream == stream
    process = processes[0]
    assert process.poll() is not None
    assert process.stdin.closed and process.stdout.closed and process.stderr.closed
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)
    recover(extension_python)


def test_exact_output_limits(extension_python):
    # UUID content varies, but its encoded length is fixed.
    length = (
        len(
            json.dumps(
                {
                    "protocol": "apizr.extension/v1",
                    "request_id": "0" * 32,
                    "operation": "describe",
                    "status": "ok",
                    "result": "ok",
                },
                separators=(",", ":"),
            ).encode()
        )
        + 1
    )
    assert (
        invoke(
            extension_python,
            {"mode": "stderr", "count": 31},
            limits=Limits(max_stdout_bytes=length, max_stderr_bytes=31),
        ).result
        == "ok"
    )
    for limits, stream in [
        (Limits(max_stdout_bytes=length - 1), "stdout"),
        (Limits(max_stderr_bytes=30), "stderr"),
        (Limits(max_stderr_bytes=0), "stderr"),
    ]:
        with pytest.raises(SizeLimitExceeded) as caught:
            invoke(extension_python, {"mode": "stderr", "count": 31}, limits=limits)
        assert caught.value.stream == stream
        recover(extension_python)


@pytest.mark.parametrize("mode", ["sleep", "closed-pipes"])
def test_timeout_even_after_closed_pipes(extension_python, tmp_path, mode):
    marker = tmp_path / "pid"
    started = time.monotonic()
    with pytest.raises(InvocationTimeout):
        invoke(
            extension_python,
            {"mode": mode, "marker": str(marker)},
            limits=Limits(wall_time_ms=700),
        )
    assert time.monotonic() - started < 5
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)
    recover(extension_python)


def test_explicit_cancellation(extension_python, tmp_path):
    cancel = threading.Event()
    marker = tmp_path / "pid"
    timer = threading.Timer(0.7, cancel.set)
    timer.start()
    try:
        with pytest.raises(InvocationCancelled):
            invoke(
                extension_python,
                {"mode": "sleep", "marker": str(marker)},
                cancel=cancel,
            )
    finally:
        timer.cancel()
        timer.join(timeout=2)
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)
    recover(extension_python)


def test_ordinary_child_holding_streams_is_killed(extension_python, tmp_path):
    marker = tmp_path / "child"
    worker = tmp_path / "worker"
    try:
        result = invoke(
            extension_python,
            {"mode": "child", "child_marker": str(marker), "marker": str(worker)},
        )
        assert result.result == "ok"
        wait_for_terminal_process(
            int(marker.read_text()), int(worker.read_text()), marker, timeout=3
        )
    finally:
        if marker.exists():
            try:
                os.kill(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
    recover(extension_python)


def test_detached_child_does_not_hold_host_forever(extension_python, tmp_path):
    marker = tmp_path / "detached"
    try:
        with pytest.raises(InvocationTimeout):
            invoke(
                extension_python,
                {"mode": "detached", "child_marker": str(marker)},
                limits=Limits(wall_time_ms=700),
            )
        # Deliberately outside the owned group: the test, not the API, cleans it.
        os.kill(int(marker.read_text()), 0)
    finally:
        if marker.exists():
            try:
                os.killpg(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
            wait_for_terminal_process(
                int(marker.read_text()), int(marker.read_text()), marker, timeout=3
            )
    recover(extension_python)


def test_input_size_validation_and_precancellation_never_spawn(
    extension_python, monkeypatch
):
    with monkeypatch.context() as context:
        context.setattr(
            supervisor.subprocess,
            "Popen",
            lambda *a, **kw: pytest.fail("must not launch"),
        )
        with pytest.raises(SizeLimitExceeded) as caught:
            invoke(
                extension_python,
                {"secret": "x" * 8192},
                limits=Limits(max_request_bytes=256),
            )
        assert caught.value.stream == "request"
        with pytest.raises(InvalidInvocation):
            invoke(extension_python, {"value": float("nan")})
        with pytest.raises(InvalidInvocation):
            invoke(extension_python, environment={"BAD=NAME": "secret"})
        with pytest.raises(InvalidInvocation):
            invoke_extension(
                extension_python, "-c", "describe", {}, limits=Limits(), environment={}
            )
        cancel = threading.Event()
        cancel.set()
        with pytest.raises(InvocationCancelled):
            invoke(extension_python, cancel=cancel)
    recover(extension_python)


def test_spawn_failure_is_redacted(extension_python, monkeypatch):
    with monkeypatch.context() as context:

        def fail(*args, **kwargs):
            raise OSError("SECRET executable path")

        context.setattr(supervisor.subprocess, "Popen", fail)
        with pytest.raises(PrerequisiteMissing) as caught:
            invoke(extension_python)
        assert "SECRET" not in "".join(traceback.format_exception(caught.value))
    recover(extension_python)


def test_cleanup_failure_is_distinct_and_closes_all_streams(monkeypatch):
    process = Mock()
    process.pid = 123
    process.poll.return_value = None
    process.wait.side_effect = subprocess.TimeoutExpired("redacted", 1)
    monkeypatch.setattr(supervisor.os, "killpg", lambda *args: None)
    with pytest.raises(CleanupFailed):
        supervisor._cleanup(process, 1)
    for stream in (process.stdin, process.stdout, process.stderr):
        stream.close.assert_called_once()


def test_cleanup_reaps_then_retries_permission_error(monkeypatch):
    process = Mock()
    process.pid = 123
    process.poll.return_value = None
    signals = Mock(side_effect=[PermissionError(), None])
    monkeypatch.setattr(supervisor.os, "killpg", signals)
    supervisor._cleanup(process, 1000)
    assert signals.call_count == 2 and process.wait.call_count == 2


@pytest.mark.parametrize(
    "module,error",
    [("invocation_unread", InvocationTimeout), ("invocation_closed", PluginFailed)],
)
def test_nonreading_stdin_is_bounded(extension_python, module, error):
    with pytest.raises(error):
        invoke_extension(
            extension_python,
            module,
            "describe",
            {"data": "x" * 524288},
            limits=Limits(wall_time_ms=700),
            environment={},
        )
    recover(extension_python)


def test_timeout_cleans_group_including_ordinary_child(extension_python, tmp_path):
    marker, worker = tmp_path / "child", tmp_path / "worker"
    try:
        with pytest.raises(InvocationTimeout):
            invoke(
                extension_python,
                {
                    "mode": "child-sleep",
                    "child_marker": str(marker),
                    "marker": str(worker),
                },
                limits=Limits(wall_time_ms=700),
            )
        wait_for_terminal_process(
            int(marker.read_text()), int(worker.read_text()), marker, timeout=3
        )
    finally:
        if marker.exists():
            try:
                os.kill(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
    recover(extension_python)


def test_signal_failure_still_reaps_direct_child_and_closes_streams(monkeypatch):
    process = Mock()
    process.pid = 123
    process.poll.return_value = None
    monkeypatch.setattr(supervisor.os, "killpg", Mock(side_effect=OSError("redacted")))
    with pytest.raises(CleanupFailed):
        supervisor._cleanup(process, 1000)
    process.kill.assert_called_once()
    process.wait.assert_called_once()
    for stream in (process.stdin, process.stdout, process.stderr):
        stream.close.assert_called_once()

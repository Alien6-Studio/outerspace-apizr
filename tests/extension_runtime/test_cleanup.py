"""A synchronized live-group -> zombie-only-group cleanup regression."""

import json
import os
import signal
import socket
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest
from execution.observation import process_state, wait_for_terminal_process

from apizr.extension_runtime import (
    CleanupFailed,
    InvocationCancelled,
    PluginFailed,
    supervisor,
)
from extension_runtime.held_group import receive, send
from extension_runtime.test_invocation import invoke, recover

pytestmark = pytest.mark.timeout(20)


@pytest.mark.parametrize("outcome", ["ok", "plugin-failed", "cancelled"])
def test_cleanup_after_group_signal(
    extension_python, tmp_path, monkeypatch, request, outcome
):
    cancel = Event()
    events = []
    processes = []
    state = {}
    real_killpg = os.killpg
    exchange = supervisor._exchange
    connection = None
    marker = tmp_path / "state"
    marker.write_text("test-owned fixture")
    fifo = tmp_path / "release"
    os.mkfifo(fifo)
    release = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)

    def observe_exchange(process, *args):
        processes.append(process)
        return exchange(process, *args)

    def signal_group(pid, sig):
        event = {"call": "killpg", "pid": pid, "signal": int(sig)}
        events.append(event)
        try:
            result = real_killpg(pid, sig)
            event["result"] = 0
        except OSError as error:
            event["errno"] = error.errno
            raise
        if pid == state.get("group") and not state.get("observed"):
            state["observed"] = True
            assert processes[0].returncode == (7 if outcome == "plugin-failed" else 0)
            # The leader is already reaped; its group member is not.
            assert connection is not None
            send(connection, "observe-exit")
            assert receive(connection) == {"event": "closed"}
            history = wait_for_terminal_process(state["child"], pid, marker)
            observed = history[-1]["process"]
            assert observed is not None and observed["state"].startswith("Z")
            assert observed["ppid"] == state["helper"]
            events.append({"event": "zombie_retained", "process": observed})
            if outcome == "cancelled":
                cancel.set()
        return result

    monkeypatch.setattr(supervisor, "_exchange", observe_exchange)
    monkeypatch.setattr(os, "killpg", signal_group)
    with tempfile.TemporaryDirectory(prefix="apizr-cleanup-") as temporary:
        with socket.socket(socket.AF_UNIX) as listener:
            address = str(Path(temporary) / "control")
            listener.bind(address)
            listener.listen(1)
            listener.settimeout(5)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    invoke,
                    extension_python,
                    {
                        "mode": "held-child",
                        "control": address,
                        "leader_release": str(fifo),
                        "fail": outcome == "plugin-failed",
                        # A test-owned, detached holder keeps one pipe open so
                        # cancellation is observed before exchange completion.
                        "keep_stderr": outcome == "cancelled",
                    },
                    cancel=cancel,
                )
                try:
                    connection, _ = listener.accept()
                    state.update(receive(connection))
                    assert state["event"] == "ready"
                    live = process_state(state["child"])
                    assert live and not live["state"].startswith("Z")
                    assert live["pgid"] == state["group"]
                    events.append({"event": "live_child_ready", "process": live})
                    os.write(release, b"x")
                    if outcome == "ok":
                        assert future.result(timeout=10).result == "ok"
                    else:
                        expected = (
                            PluginFailed
                            if outcome == "plugin-failed"
                            else InvocationCancelled
                        )
                        with pytest.raises(expected):
                            future.result(timeout=10)
                finally:
                    try:
                        if connection is not None:
                            send(connection, "reap")
                            reaped = receive(connection)
                            assert reaped["event"] == "reaped"
                            assert reaped["pid"] == state["child"]
                            assert os.WIFSIGNALED(reaped["status"])
                            assert os.WTERMSIG(reaped["status"]) == signal.SIGKILL
                            events.append(reaped)
                            connection.close()
                            wait_for_terminal_process(
                                state["helper"], state["helper"], marker
                            )
                            assert process_state(state["child"]) is None
                    finally:
                        os.close(release)
                        for pid in (state.get("child"), state.get("helper")):
                            if pid:
                                try:
                                    os.kill(pid, signal.SIGKILL)
                                except ProcessLookupError:
                                    pass
                        for process in processes:
                            assert process.returncode is not None
                            assert all(
                                stream.closed
                                for stream in (
                                    process.stdin,
                                    process.stdout,
                                    process.stderr,
                                )
                            )
                            with pytest.raises(ChildProcessError):
                                os.waitpid(process.pid, os.WNOHANG)
                        request.node.user_properties.append(
                            ("cleanup_trace", json.dumps(events))
                        )
                        recover(extension_python)


def test_denied_group_signal_is_not_treated_as_success(monkeypatch):
    process = Mock()
    process.pid = 123
    process.poll.return_value = None
    denied = Mock(side_effect=PermissionError(1, "test denial"))
    monkeypatch.setattr(supervisor.os, "killpg", denied)
    with pytest.raises(CleanupFailed):
        supervisor._cleanup(process, 1000)
    assert denied.call_count == 2
    assert process.kill.called and process.wait.called
    for stream in (process.stdin, process.stdout, process.stderr):
        stream.close.assert_called_once()

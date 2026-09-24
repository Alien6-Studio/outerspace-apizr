"""First-signal EPERM, unlike the already-successful signal in #125."""

import errno
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from execution.observation import process_state, wait_for_terminal_process
from extension_runtime.held_group import receive, send

from apizr.git_source import AcquisitionLimits, GitSourceError
from apizr.git_source.process import GitRunner

pytestmark = pytest.mark.timeout(20)


@pytest.mark.parametrize("release", [True, False], ids=["reaped", "unconfirmed"])
def test_zombie_before_first_group_signal(tmp_path, monkeypatch, request, release):
    events, processes = [], []
    state = {}
    connection = None
    reaped = False
    real_killpg, popen = os.killpg, subprocess.Popen
    marker = tmp_path / "observation"
    marker.write_text("stable")

    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        if kwargs.get("start_new_session"):
            processes.append(process)
        return process

    def reap():
        nonlocal reaped
        send(connection, "reap")
        result = receive(connection)
        assert result["event"] == "reaped"
        assert os.WIFEXITED(result["status"]) and os.WEXITSTATUS(result["status"]) == 23
        reaped = True
        events.append(result)

    def signal_group(pid, sig):
        event = {"call": "killpg", "pid": pid, "signal": int(sig)}
        events.append(event)
        try:
            result = real_killpg(pid, sig)
            event["result"] = 0
            return result
        except OSError as error:
            event["errno"] = error.errno
            if error.errno == errno.EPERM and pid == state.get("group"):
                event["child"] = process_state(state["child"])
                event["leader_returncode"] = processes[0].returncode
                assert event["child"]["state"].startswith("Z")
                assert event["child"]["ppid"] == state["helper"]
                assert processes[0].returncode == 128
                # Retain the zombie across the original three immediate calls.
                # Reaping is explicitly acknowledged, never timed with a sleep.
                denials = sum(e.get("errno") == errno.EPERM for e in events)
                if release and denials == 3:
                    reap()
            raise

    monkeypatch.setattr(subprocess, "Popen", capture)
    monkeypatch.setattr(os, "killpg", signal_group)
    with tempfile.TemporaryDirectory(prefix="az-git-cleanup-") as directory:
        work = Path(directory)
        fifo = work / "release"
        os.mkfifo(fifo)
        gate = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
        address = str(work / "control")
        wrapper = work / "git"
        wrapper.write_text(
            f"#!{sys.executable}\nimport os,sys\n"
            f"sys.path.insert(0,{str(Path(__file__).parents[1])!r})\n"
            "from git_source.held_zombie import hold\n"
            f"if os.fork()==0: hold({address!r})\n"
            f"with open({str(fifo)!r},'rb',buffering=0) as gate: gate.read(1)\n"
            "os._exit(128)\n"
        )
        wrapper.chmod(0o700)
        runner = GitRunner(
            str(wrapper), work, AcquisitionLimits(total_timeout_ms=5000), None, None
        )
        with (
            socket.socket(socket.AF_UNIX) as listener,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            listener.bind(address)
            listener.listen(1)
            listener.settimeout(5)
            future = pool.submit(runner.run, [])
            try:
                connection, _ = listener.accept()
                state.update(receive(connection))
                send(connection, "exit-child")
                assert receive(connection) == {"event": "released"}
                history = wait_for_terminal_process(
                    state["child"], state["group"], marker
                )
                events.append(
                    {"event": "before_first_signal", "process": history[-1]["process"]}
                )
                started = time.monotonic()
                os.write(gate, b"x")
                code = (
                    "git_cleanup_failed"
                    if sys.platform == "darwin" and not release
                    else "git_command_failed"
                )
                with pytest.raises(GitSourceError, match=f"^{code}$"):
                    future.result(timeout=5)
                elapsed = time.monotonic() - started
                assert elapsed < 3.5
                events.append({"event": "result", "code": code, "seconds": elapsed})
                if sys.platform == "darwin":
                    assert any(e.get("errno") == errno.EPERM for e in events)
                else:
                    assert any(e.get("result") == 0 for e in events)
            finally:
                try:
                    if connection is not None and not reaped:
                        reap()
                    if connection is not None:
                        connection.close()
                    if state:
                        wait_for_terminal_process(
                            state["helper"], state["helper"], marker
                        )
                        assert process_state(state["child"]) is None
                finally:
                    os.close(gate)
                    for process in processes:
                        if process.poll() is None:
                            real_killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=2)
                        assert process.stdout.closed and process.stderr.closed
                        with pytest.raises(ChildProcessError):
                            os.waitpid(process.pid, os.WNOHANG)
                    request.node.user_properties.append(
                        ("cleanup_trace", json.dumps(events))
                    )
        # A fresh invocation still works after both the confirmed and denied paths.
        runner = GitRunner(sys.executable, work, AcquisitionLimits(), None, None)
        runner.command = [sys.executable, "-I", "-c", "print('ok')"]
        assert runner.run([]) == b"ok\n"

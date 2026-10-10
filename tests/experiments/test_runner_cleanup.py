"""Ready/live descendants, real deadline and Ctrl-C persist terminal evidence."""

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from execution.observation import process_state, wait_for_terminal_process
from extension_runtime.held_group import receive, send

from apizr.experiments import runner
from apizr.experiments.history import show_run
from apizr.experiments.planning import RunOptions
from apizr.experiments.store import DEFAULT_STORE

pytestmark = pytest.mark.timeout(25)


@pytest.mark.parametrize("finish", ["success", "timeout", "cancel"])
def test_synchronized_descendant_group_cleanup(tmp_path, monkeypatch, request, finish):
    marker = tmp_path / "identity"
    heartbeat = tmp_path / "heartbeat"
    processes = []
    popen = subprocess.Popen

    def spawn(*args, **kwargs):
        process = popen(*args, **kwargs)
        if kwargs.get("start_new_session"):
            processes.append(process)
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", spawn)
    expired = threading.Event()
    # Startup is outside the test's timing assumption: arm the deadline only
    # after the OS observation proves a live descendant in the worker group.
    monotonic = time.monotonic
    monkeypatch.setattr(
        runner,
        "time",
        SimpleNamespace(
            monotonic=lambda: monotonic() + (120 if expired.is_set() else 0)
        ),
    )
    with tempfile.TemporaryDirectory(prefix="az-264-") as folder:
        address = str(Path(folder) / "control")
        child = f"""import json, os, socket, time
from pathlib import Path
identity = {{"pid": os.getpid(), "pgid": os.getpgrp(), "worker": os.getppid()}}
Path({str(marker)!r}).write_text(json.dumps(identity))
Path({str(heartbeat)!r}).write_text("ready")
with socket.socket(socket.AF_UNIX) as channel:
    channel.connect({address!r})
    channel.sendall(json.dumps(identity).encode() + b"\\n")
    assert channel.recv(32) == b'"finish"\\n'
os.write(int(os.environ['NOTIFY']), b'x')
while True:
    Path({str(heartbeat)!r}).write_text(str(time.monotonic()))
    time.sleep(.02)
"""
        source = tmp_path / "train.py"
        source.write_text(f"""import os, subprocess, sys, time
ready, notify = os.pipe()
subprocess.Popen([sys.executable, "-I", "-c", {child!r}], env={{"NOTIFY": str(notify)}}, pass_fds=(notify,))
os.close(notify)
assert os.read(ready, 1) == b'x'
os.close(ready)
{"" if finish == "success" else "time.sleep(120)"}
""")
        identity = None
        with (
            socket.socket(socket.AF_UNIX) as listener,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            listener.bind(address)
            listener.listen(1)
            listener.settimeout(10)
            future = pool.submit(runner.run_experiment, source)
            try:
                with listener.accept()[0] as connection:
                    identity = receive(connection)
                    state = process_state(identity["pid"])
                    assert state and not state["state"].startswith("Z")
                    assert state["pgid"] == identity["pgid"] == identity["worker"]
                    send(connection, "finish")
                    if finish == "timeout":
                        expired.set()
                    elif finish == "cancel":
                        # Worker KeyboardInterrupt and group cleanup are exercised
                        # here; the separate CLI test sends SIGINT to the parent.
                        os.kill(identity["worker"], signal.SIGINT)
                record = future.result(timeout=5)
                assert (
                    record.run.status
                    == {
                        "success": "success",
                        "timeout": "failed",
                        "cancel": "cancelled",
                    }[finish]
                )
                if finish != "success":
                    assert (
                        record.run.diagnostics[0].code
                        == {
                            "timeout": "execution_timeout",
                            "cancel": "execution_cancelled",
                        }[finish]
                    )
                trace = wait_for_terminal_process(
                    identity["pid"], identity["pgid"], heartbeat
                )
                assert show_run(tmp_path / DEFAULT_STORE, record.run_digest) == record
                request.node.user_properties.append(
                    ("experiment_descendant_trace", json.dumps(trace))
                )
            finally:
                for process in processes:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=2)
                if identity is None and marker.exists():
                    identity = json.loads(marker.read_text())
                if identity is not None:
                    state = process_state(identity["pid"])
                    if state and not state["state"].startswith("Z"):
                        os.kill(identity["pid"], signal.SIGKILL)
                future.result(timeout=5)
            for process in processes:
                assert process.stdin.closed and process.stdout.closed
                with pytest.raises(ChildProcessError):
                    os.waitpid(process.pid, os.WNOHANG)


@pytest.mark.parametrize("closed", [False, True])
def test_real_timeout_includes_worker_without_response_pipe(tmp_path, closed):
    source = tmp_path / "train.py"
    source.write_text(
        "import os, time\n"
        + ("os.closerange(0, 1024)\n" if closed else "")
        + "time.sleep(60)"
    )
    start = time.monotonic()
    record = runner.run_experiment(source, options=RunOptions(timeout_ms=800))
    assert time.monotonic() - start < 5
    assert record.run.status == "failed"
    assert record.run.diagnostics[0].code == "execution_timeout"


def test_parent_cli_sigint_persists_cancelled_run(tmp_path):
    source = tmp_path / "train.py"
    source.write_text(
        'import os, time\nfrom pathlib import Path\nPath("ready").write_text(str(os.getpid()))\ntime.sleep(60)'
    )
    command = [
        sys.executable,
        "-I",
        "-B",
        "-m",
        "apizr.cli",
        "experiment",
        "run",
        str(source),
        "--format",
        "json",
    ]
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True
    ) as process:
        try:
            deadline = time.monotonic() + 10
            while not (tmp_path / "ready").exists():
                assert process.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.01)
            process.send_signal(signal.SIGINT)
            output, error = process.communicate(timeout=5)
            assert process.returncode == 1, error
            result = json.loads(output)
            assert result["status"] == "cancelled"
            record = show_run(tmp_path / DEFAULT_STORE, result["run_digest"])
            assert record.run.diagnostics[0].code == "execution_cancelled"
            assert process_state(int((tmp_path / "ready").read_text())) is None
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            if (tmp_path / "ready").exists():
                try:
                    os.killpg(int((tmp_path / "ready").read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

"""A readiness handshake, not a startup-speed assumption, arms cleanup assertions."""

import json
import os
import signal
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from extension_runtime.held_group import receive, send

from .observation import process_state, wait_for_terminal_process


def assert_descendant_cleanup(invoke, tmp_path, monkeypatch, request):
    marker, heartbeat = tmp_path / "descendant", tmp_path / "heartbeat"
    processes, events = [], []
    original = subprocess.Popen
    identity = None
    connection = None

    def spawn(*args, **kwargs):
        process = original(*args, **kwargs)
        if kwargs.get("start_new_session"):
            processes.append(process)
            events.append(
                {"event": "worker_spawned", "pid": process.pid, "at": time.monotonic()}
            )
        return process

    monkeypatch.setattr(subprocess, "Popen", spawn)
    with tempfile.TemporaryDirectory(prefix="az-descendant-") as directory:
        address = str(Path(directory) / "control")
        child = f"""import json,os,socket,sys,time
from pathlib import Path
identity={{"pid":os.getpid(),"pgid":os.getpgrp(),"worker":os.getppid()}}
marker=Path({str(marker)!r})
marker.with_suffix('.new').write_text(json.dumps(identity))
marker.with_suffix('.new').replace(marker)
heartbeat=Path({str(heartbeat)!r});heartbeat.write_text("ready")
with socket.socket(socket.AF_UNIX) as channel:
 channel.settimeout(5);channel.connect({address!r})
 channel.sendall(json.dumps(identity).encode()+b"\\n")
 assert channel.recv(32)==b'"finish"\\n'
os.write(int(sys.argv[1]),b'x');os.close(int(sys.argv[1]))
while True:
 heartbeat.write_text(str(time.monotonic()))
 time.sleep(.02)
"""
        source = f"""import os,subprocess,sys

def f():
    ready, notify = os.pipe()
    try:
        subprocess.Popen([sys.executable,"-I","-c",{child!r},str(notify)],pass_fds=(notify,))
    finally:
        os.close(notify)
    try:
        assert os.read(ready,1)==b"x"
    finally:
        os.close(ready)
    return "ready"
"""
        with (
            socket.socket(socket.AF_UNIX) as listener,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            listener.bind(address)
            listener.listen(1)
            listener.settimeout(5)
            # Use the ordinary invocation policy. Completion is triggered by the
            # handshake; the separate timeout tests retain their original budgets.
            future = pool.submit(invoke, source)
            try:
                connection, _ = listener.accept()
                identity = receive(connection)
                state = process_state(identity["pid"])
                assert state and not state["state"].startswith("Z")
                assert state["pgid"] == identity["pgid"] == identity["worker"]
                assert heartbeat.exists()
                events.append(
                    {
                        "event": "descendant_ready",
                        "process": state,
                        "at": time.monotonic(),
                    }
                )
                send(connection, "finish")
                result = future.result(timeout=7)
                events.append(
                    {"event": "result", "status": result.status, "at": time.monotonic()}
                )
                assert result.status == "success" and result.value == "ready", result
                history = wait_for_terminal_process(
                    identity["pid"], identity["pgid"], heartbeat
                )
                events.append({"event": "descendant_terminal", "history": history})
            except BaseException:
                if future.done():
                    result = future.result()
                    events.append(
                        {"event": "preparation_failed", "status": result.status}
                    )
                raise
            finally:
                try:
                    if connection is not None:
                        connection.close()
                    # This also covers failure before the host received readiness.
                    # Do not let the executor context wait on a stranded fixture.
                    for process in processes:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=2)
                    if identity is None and marker.exists():
                        identity = json.loads(marker.read_text())
                    if identity is not None:
                        state = process_state(identity["pid"])
                        if state and not state["state"].startswith("Z"):
                            assert state["pgid"] == identity["pgid"]
                            os.kill(identity["pid"], signal.SIGKILL)
                        if heartbeat.exists():
                            wait_for_terminal_process(
                                identity["pid"], identity["pgid"], heartbeat
                            )
                    future.result(timeout=3)
                    for process in processes:
                        assert process.stdin.closed and process.stdout.closed
                        try:
                            os.waitpid(process.pid, os.WNOHANG)
                        except ChildProcessError:
                            pass
                        else:
                            raise AssertionError("direct worker was not reaped")
                finally:
                    request.node.user_properties.append(
                        ("descendant_trace", json.dumps(events))
                    )

"""Bounded, test-only observation of the unchanged generated execution runtime.

The worker still runs its verified script under the same isolated interpreter.
Only fixed phase names, timings, process/pipe state and interpreter identity are
recorded in separate files; no request, result, environment or exception text.
"""

import atexit
import importlib.machinery
import json
import os
import runpy
import sys
import time
from pathlib import Path
from types import SimpleNamespace

MAX_TRACE_BYTES = 65536


class Trace:
    def __init__(self, directory):
        self.path = Path(directory) / f"process-{os.getpid()}.jsonl"
        self.size = 0
        self.limited = False

    def emit(self, phase, **fields):
        if self.limited:
            return
        event = dict(phase=phase, ns=time.monotonic_ns(), pid=os.getpid(), **fields)
        raw = (json.dumps(event, sort_keys=True) + "\n").encode()
        if self.size + len(raw) > MAX_TRACE_BYTES - 128:
            raw = b'{"phase":"trace_limit"}\n'
            self.limited = True
        with self.path.open("ab") as target:
            target.write(raw)
        self.size += len(raw)

    def identity(self, phase):
        self.emit(
            phase,
            executable=sys.executable,
            version=sys.version,
            architecture=os.uname().machine,
        )

    def wrap(self, phase, function):
        def measured(*args, **kwargs):
            self.emit(phase + "_begin")
            try:
                return function(*args, **kwargs)
            finally:
                self.emit(phase + "_end")

        return measured


def instrument_worker(module, trace):
    trace.emit("imports_complete")
    for name, phase in [
        ("read_frame", "receive"),
        ("validate_plan", "validate_plan"),
        ("load_source", "load_source"),
        ("arguments", "bind_arguments"),
        ("frame", "response_frame"),
        ("handle", "handle"),
        ("main", "worker_main"),
    ]:
        setattr(module, name, trace.wrap(phase, getattr(module, name)))
    module.Request.model_validate = staticmethod(
        trace.wrap("validate_request", module.Request.model_validate)
    )
    original_binding = module.verify_binding

    def binding(*args, **kwargs):
        function = original_binding(*args, **kwargs)
        if module.asyncio.iscoroutinefunction(function):

            async def measured(*args, **kwargs):
                trace.emit("calculation_begin")
                try:
                    return await function(*args, **kwargs)
                finally:
                    trace.emit("calculation_end")

            return measured
        return trace.wrap("calculation", function)

    module.verify_binding = binding


def worker(directory, script):
    trace = Trace(directory)
    trace.identity("worker_boot")
    atexit.register(trace.emit, "interpreter_atexit")

    class Finder:
        @staticmethod
        def find_spec(fullname, path, target=None):
            if fullname != "apizr_governed.execution.worker":
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
            assert spec is not None and spec.loader is not None
            original = spec.loader

            class Loader:
                @staticmethod
                def create_module(spec):
                    return original.create_module(spec)

                @staticmethod
                def exec_module(module):
                    original.exec_module(module)
                    instrument_worker(module, trace)

            spec.loader = Loader()
            return spec

    finder = Finder()
    sys.meta_path.insert(0, finder)
    try:
        sys.argv = [script]
        runpy.run_path(script, run_name="__main__")
    finally:
        trace.emit("worker_exit")
        sys.meta_path.remove(finder)


def install_server(root):
    """Inject observers in the test process, never into generated artifacts."""
    directory = root.parent / "phases"
    directory.mkdir()
    trace = Trace(directory)
    trace.identity("server_boot")
    # Load the embedded package without starting the transport. The real server
    # bootstrap and its audit hook still run; generated artifacts are unchanged.
    runpy.run_path(str(root / "server.py"), run_name="qualification_probe")
    supervisor = sys.modules["apizr_governed.execution.supervisor"]
    original_exchange = supervisor.exchange
    original_cleanup = supervisor.kill_group
    original_subprocess = supervisor.subprocess
    current = {"call": 0, "process": None}

    def emit(phase, **fields):
        trace.emit(phase, call=current["call"], **fields)

    class Popen(original_subprocess.Popen):
        def __init__(self, *args, **kwargs):
            emit("launch_begin")
            super().__init__(*args, **kwargs)
            current["process"] = self
            emit("launch_end", child=self.pid)

        def wait(self, *args, **kwargs):
            emit("wait_begin", child=self.pid)
            try:
                return super().wait(*args, **kwargs)
            finally:
                emit("wait_end", child=self.pid, returncode=self.returncode)

    class ObservedOS:
        def __getattr__(self, name):
            return getattr(os, name)

        @staticmethod
        def write(fd, data):
            count = os.write(fd, data)
            emit("request_write", count=count)
            return count

        @staticmethod
        def read(fd, size):
            data = os.read(fd, size)
            emit("response_read", count=len(data))
            return data

    def cleanup(process):
        emit("cleanup_begin", child=process.pid)
        try:
            return original_cleanup(process)
        finally:
            emit("cleanup_end", child=process.pid, returncode=process.returncode)

    def exchange(command, payload, work, environment, wall_time_ms, output_limit):
        current["call"] += 1
        current["process"] = None
        assert current["call"] <= 128, "qualification call bound"
        emit("exchange_begin", budget_ms=wall_time_ms)
        assert command[1] == "-I" and len(command) == 3
        observed = [command[0], "-I", __file__, "worker", str(directory), command[2]]
        status = "exception"
        try:
            result = original_exchange(
                observed, payload, work, environment, wall_time_ms, output_limit
            )
            status = result.status
            return result
        finally:
            process = current["process"]
            emit(
                "exchange_end",
                status=status,
                child=process.pid if process else None,
                reaped=process is not None and process.returncode is not None,
                stdin_closed=process is not None and process.stdin.closed,
                stdout_closed=process is not None and process.stdout.closed,
            )

    supervisor.subprocess = SimpleNamespace(
        Popen=Popen,
        PIPE=original_subprocess.PIPE,
        DEVNULL=original_subprocess.DEVNULL,
        TimeoutExpired=original_subprocess.TimeoutExpired,
    )
    supervisor.os = ObservedOS()
    supervisor.kill_group = cleanup
    supervisor.exchange = exchange


if __name__ == "__main__":
    assert sys.argv[1] == "worker" and len(sys.argv) == 4
    worker(sys.argv[2], sys.argv[3])

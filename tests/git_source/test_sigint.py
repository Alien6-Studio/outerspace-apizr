"""Deterministic SIGINT at subprocess ownership/lock boundaries."""

import os
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from apizr.git_source.models import AcquisitionLimits
from apizr.git_source.process import GitRunner


@pytest.mark.timeout(10)
@pytest.mark.parametrize("boundary", ["poll-lock", "spawn", "cleanup"])
def test_interrupt_does_not_strand_child_or_wait_lock(tmp_path, monkeypatch, boundary):
    processes = []
    locks = []
    fired = False
    popen = subprocess.Popen
    previous = signal.getsignal(signal.SIGINT)

    def interrupt():
        nonlocal fired
        if not fired:
            fired = True
            os.kill(os.getpid(), signal.SIGINT)

    class InterruptLock:
        def __init__(self, lock):
            self.lock = lock

        def acquire(self, blocking=True):
            acquired = self.lock.acquire(blocking)
            if acquired:
                interrupt()  # SIGINT while Popen owns its waitpid lock.
            return acquired

        def release(self):
            self.lock.release()

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *args):
            self.release()

    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        if boundary == "spawn":
            interrupt()  # Child exists, before the caller receives its handle.
        if boundary == "poll-lock":
            lock = process._waitpid_lock
            locks.append(lock)
            process._waitpid_lock = InterruptLock(lock)
        if boundary == "cleanup":
            wait = process.wait

            def cleanup(*args, **kwargs):
                result = wait(*args, **kwargs)
                interrupt()
                return result

            process.wait = cleanup
        return process

    monkeypatch.setattr(subprocess, "Popen", capture)
    runner = GitRunner(sys.executable, tmp_path, AcquisitionLimits(), None, None)
    runner.command = [
        sys.executable,
        "-I",
        "-c",
        "print('done')" if boundary == "cleanup" else "import time; time.sleep(30)",
    ]
    try:
        with pytest.raises(KeyboardInterrupt):
            runner.run([])
        assert fired and signal.getsignal(signal.SIGINT) is previous
        for process in processes:
            assert process.returncode is not None
            assert process.stdout.closed and process.stderr.closed
            with pytest.raises(ChildProcessError):
                os.waitpid(process.pid, os.WNOHANG)
        assert all(not lock.locked() for lock in locks)
    finally:
        # Keep the regression safe even against the original broken code.
        for lock in locks:
            if lock.locked():
                lock.release()
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
            process.stdout.close()
            process.stderr.close()
    monkeypatch.setattr(subprocess, "Popen", popen)
    runner.command = [sys.executable, "-I", "-c", "print('recovered')"]
    assert runner.run([]) == b"recovered\n"


def test_custom_handler_and_worker_thread_are_preserved(tmp_path):
    previous = signal.getsignal(signal.SIGINT)

    def handler(signum, frame):
        pass

    runner = GitRunner(sys.executable, tmp_path, AcquisitionLimits(), None, None)
    runner.command = [sys.executable, "-I", "-c", "print('ok')"]
    try:
        signal.signal(signal.SIGINT, handler)
        assert runner.run([]) == b"ok\n"
        assert signal.getsignal(signal.SIGINT) is handler
    finally:
        signal.signal(signal.SIGINT, previous)
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(runner.run, []).result(timeout=5) == b"ok\n"
    assert signal.getsignal(signal.SIGINT) is previous

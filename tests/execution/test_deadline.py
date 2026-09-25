"""Short execution deadlines include launch; functional recovery has its own budget."""

import os
import selectors
import sys
import time
from types import SimpleNamespace

import pytest

from apizr.execution import supervisor
from apizr.execution.model import ExecutionResult
from apizr.execution.policy import Limits
from apizr.execution.protocol import encode, frame

pytestmark = pytest.mark.timeout(15)


@pytest.fixture
def children(monkeypatch):
    original = supervisor.subprocess.Popen
    processes = []

    def launch(*args, **kwargs):
        child = original(*args, **kwargs)
        processes.append(child)
        return child

    monkeypatch.setattr(supervisor.subprocess, "Popen", launch)
    try:
        yield processes
    finally:
        # These controlled workers never spawn descendants. Keep cleanup even if
        # a regression causes the assertions below to fail before recovery.
        for child in processes:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)
            child.stdin.close()
            child.stdout.close()


def assert_clean(child):
    assert child.returncode is not None, "runtime did not reap its child"
    assert child.stdin.closed and child.stdout.closed
    with pytest.raises(ChildProcessError):
        os.waitpid(child.pid, os.WNOHANG)


def recover(root, processes):
    response = frame(
        encode(ExecutionResult(status="success", value=7).model_dump(), 128)
    )
    result = supervisor.exchange(
        [sys.executable, "-I", "-c", f"import os; os.write(1, {response!r})"],
        b"x",
        root,
        {},
        Limits().wall_time_ms,
        128,
    )
    assert result.status == "success" and result.value == 7
    assert_clean(processes[-1])


def test_deadline_already_spent_in_popen_is_not_restarted(
    tmp_path, monkeypatch, children
):
    """Advance an injected clock at a real Popen return, without sleeping.

    A relocated post-Popen deadline would attempt I/O and fail the test. This
    models a slow OS launch deterministically instead of relying on runner load.
    """
    elapsed = 0.0
    launch = supervisor.subprocess.Popen

    def slow_launch(*args, **kwargs):
        nonlocal elapsed
        child = launch(*args, **kwargs)
        elapsed = 0.2
        return child

    class NoPolling(selectors.DefaultSelector):
        def select(self, timeout=None):
            pytest.fail("I/O attempted after launch consumed the 100 ms budget")

    with monkeypatch.context() as context:
        context.setattr(supervisor.subprocess, "Popen", slow_launch)
        context.setattr(supervisor, "time", SimpleNamespace(monotonic=lambda: elapsed))
        context.setattr(
            supervisor,
            "selectors",
            SimpleNamespace(
                DefaultSelector=NoPolling,
                EVENT_WRITE=selectors.EVENT_WRITE,
                EVENT_READ=selectors.EVENT_READ,
            ),
        )
        result = supervisor.exchange(
            [sys.executable, "-I", "-c", "import signal; signal.pause()"],
            b"x",
            tmp_path,
            {},
            100,
            128,
        )
    assert result.status == "timeout"
    assert_clean(children[-1])
    recover(tmp_path, children)


@pytest.mark.parametrize(
    "code",
    [
        "import signal; signal.pause()",  # No request reception/startup completion.
        "import os,signal; os.read(0,1); signal.pause()",  # Received, no response.
    ],
)
def test_short_real_deadline_reaps_closes_and_recovers(tmp_path, children, code):
    started = time.monotonic()
    result = supervisor.exchange(
        [sys.executable, "-I", "-c", code], b"x", tmp_path, {}, 100, 128
    )
    assert result.status == "timeout"
    assert time.monotonic() - started >= 0.1
    assert_clean(children[-1])
    recover(tmp_path, children)

"""An asynchronous observation must still reject live or unobservable children."""

import os
import signal
import subprocess
import sys

import pytest

from . import observation


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, duration):
            self.now += duration

    clock = Clock()
    monkeypatch.setattr(observation.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(observation.time, "sleep", clock.sleep)
    return clock


@pytest.fixture
def heartbeat(tmp_path):
    path = tmp_path / "heartbeat"
    path.write_text("last activity")
    return path


def test_transient_nonterminal_state_requires_actual_termination(
    clock, heartbeat, monkeypatch
):
    states = iter(["D", "S", "Z"])
    monkeypatch.setattr(
        observation,
        "process_state",
        lambda pid: {"state": next(states), "pgid": 100, "ppid": 1},
    )
    history = observation.wait_for_terminal_process(101, 100, heartbeat)
    assert [sample["process"]["state"] for sample in history] == ["D", "S", "Z"]
    assert clock.now > 0


@pytest.mark.parametrize("state", ["D", "R", "S", "T"])
def test_unchanged_heartbeat_cannot_pass_nonterminal_process(
    clock, heartbeat, monkeypatch, state
):
    monkeypatch.setattr(
        observation,
        "process_state",
        lambda pid: {"state": state, "pgid": 100, "ppid": 1},
    )
    monkeypatch.setattr(
        observation, "kernel_diagnostics", lambda pid: {"SigPnd": "00000100"}
    )
    with pytest.raises(AssertionError, match="did not reach terminal state") as error:
        observation.wait_for_terminal_process(101, 100, heartbeat, timeout=0.1)
    assert "SigPnd" in str(error.value) and state in str(error.value)
    assert clock.now == pytest.approx(0.1)


@pytest.mark.parametrize("state", [None, "D", "Z"])
def test_resumed_activity_fails_even_if_process_then_terminates(
    clock, heartbeat, monkeypatch, state
):
    def resumed(pid):
        heartbeat.write_text("new activity")
        return {"state": state, "pgid": 100, "ppid": 1} if state else None

    monkeypatch.setattr(observation, "process_state", resumed)
    with pytest.raises(AssertionError, match="resumed activity"):
        observation.wait_for_terminal_process(101, 100, heartbeat)


def test_process_group_mismatch_is_not_terminal_evidence(clock, heartbeat, monkeypatch):
    monkeypatch.setattr(
        observation,
        "process_state",
        lambda pid: {"state": "Z", "pgid": 999, "ppid": 1},
    )
    with pytest.raises(AssertionError, match="identity/group changed"):
        observation.wait_for_terminal_process(101, 100, heartbeat)


@pytest.mark.parametrize(
    "code,output,error",
    [(2, "", "denied"), (1, "", "denied"), (0, "", ""), (0, "D broken 1", "")],
)
def test_invalid_observation_is_not_disappearance(monkeypatch, code, output, error):
    monkeypatch.setattr(
        observation.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, code, output, error),
    )
    with pytest.raises((AssertionError, ValueError)):
        observation.process_state(101)


def test_disappearance_requires_the_ps_no_process_result(monkeypatch):
    monkeypatch.setattr(
        observation.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "", ""),
    )
    assert observation.process_state(101) is None


@pytest.mark.timeout(5)
def test_real_stopped_child_with_no_activity_is_rejected(heartbeat):
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    try:
        os.kill(child.pid, signal.SIGSTOP)
        with pytest.raises(AssertionError, match="did not reach terminal state"):
            observation.wait_for_terminal_process(
                child.pid, child.pid, heartbeat, timeout=0.1
            )
    finally:
        child.kill()
        child.wait(timeout=2)

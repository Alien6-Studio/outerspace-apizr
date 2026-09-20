"""Provider observations use a fake monotonic clock, never real sleeps."""

import json
import subprocess

import pytest

from apizr.oci import docker
from apizr.oci.docker import DockerProvider
from apizr.oci.provider import ProviderError


def state(*, running=False, status="exited", oom=False, code=137):
    return {"Running": running, "Status": status, "OOMKilled": oom, "ExitCode": code}


@pytest.fixture
def observation(monkeypatch):
    now = [0.0]
    calls = []
    sleeps = []
    monkeypatch.setattr(docker.time, "monotonic", lambda: now[0])

    def sleep(seconds):
        assert 0 < seconds <= 0.05
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(docker.time, "sleep", sleep)

    def observe(sequence, timeout=1.0):
        def run(self, args, **kwargs):
            assert args == ["inspect", "--format", "{{json .State}}", "test"]
            assert 0 < kwargs["timeout"] <= timeout - now[0] + 1e-8
            item = sequence[min(len(calls), len(sequence) - 1)]
            calls.append(item)
            if isinstance(item, Exception):
                raise item
            return item if isinstance(item, bytes) else json.dumps(item).encode()

        monkeypatch.setattr(DockerProvider, "run", run)
        result = DockerProvider().final_state("test", timeout=timeout)
        return result, now[0], calls, sleeps

    return observe


def test_running_then_exit_then_delayed_oom(observation):
    result, elapsed, calls, sleeps = observation(
        [state(running=True, status="running", code=0), state(), state(oom=True)]
    )
    assert result.terminal and result.oom_killed and result.exit_code == 137
    assert len(calls) == 3 and elapsed == pytest.approx(0.1) and len(sleeps) == 2


@pytest.mark.parametrize("code", [1, 23, 126, 255])
def test_ordinary_terminal_failure_returns_without_sleep(observation, code):
    result, elapsed, calls, sleeps = observation([state(code=code)])
    assert result.terminal and not result.oom_killed and result.exit_code == code
    assert elapsed == 0 and len(calls) == 1 and not sleeps


@pytest.mark.parametrize("code", [0, 137])
def test_ambiguous_exit_never_guesses_oom(observation, code):
    result, elapsed, calls, sleeps = observation([state(code=code)])
    assert result.terminal and not result.oom_killed
    assert elapsed == pytest.approx(1.0) and 1 < len(calls) <= 21 and sleeps


@pytest.mark.parametrize(
    "initial",
    [
        ProviderError(),
        b"not JSON",
        b"{}",
        state(running=True, status="exited", oom=True),
    ],
)
def test_transient_unavailable_or_incoherent_evidence_recovers(observation, initial):
    result, elapsed, calls, _ = observation([initial, state(oom=True)])
    assert result.oom_killed and result.terminal
    assert len(calls) == 2 and elapsed == pytest.approx(0.05)


@pytest.mark.parametrize(
    "bad",
    [
        ProviderError(),
        b"[]",
        b"null",
        b"{",
        b"{}",
        {"OOMKilled": True},
        state(running=True, status="running", oom=True),
        state(status="created", oom=True),
        state(status="restarting", oom=True),
        state(status="unknown", oom=True),
        state(oom="true"),
        state(running="false"),
        state(code="137"),
        state(code=True),
    ],
)
def test_persistent_invalid_or_nonterminal_state_is_bounded(observation, bad):
    result, elapsed, calls, _ = observation([bad], timeout=0.12)
    assert result is None
    assert elapsed == pytest.approx(0.12) and len(calls) == 3


def test_dead_state_with_oom_evidence_is_terminal(observation):
    result, elapsed, _, _ = observation([state(status="dead", oom=True)])
    assert result.terminal and result.oom_killed and elapsed == 0


def test_observation_timeout_bounds_each_cli_call(monkeypatch):
    now = [0.0]
    calls = []
    monkeypatch.setattr(docker.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(
        docker.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds)
    )

    def slow(*args, **kwargs):
        calls.append(kwargs["timeout"])
        now[0] += kwargs["timeout"]
        raise subprocess.TimeoutExpired("PRIVATE", kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", slow)
    assert DockerProvider().final_state("test", timeout=0.12) is None
    assert sum(calls) <= 0.12 and now[0] == pytest.approx(0.12)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_observation_timeout_is_rejected(timeout):
    with pytest.raises(ValueError):
        DockerProvider().final_state("test", timeout=timeout)

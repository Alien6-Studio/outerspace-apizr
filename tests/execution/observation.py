"""Test-only terminal-state evidence, never a production cleanup mechanism."""

import subprocess
import time
from pathlib import Path


def process_state(pid):
    result = subprocess.run(
        ["ps", "-o", "stat=", "-o", "pgid=", "-o", "ppid=", "-p", str(pid)],
        capture_output=True,
        text=True,
        timeout=0.5,
        check=False,
    )
    if (
        result.returncode == 1
        and not result.stdout.strip()
        and not result.stderr.strip()
    ):
        return None
    assert result.returncode == 0, f"ps failed: {result.stderr!r}"
    fields = result.stdout.split()
    assert len(fields) == 3, f"Invalid ps observation: {result.stdout!r}"
    return {"state": fields[0], "pgid": int(fields[1]), "ppid": int(fields[2])}


def kernel_diagnostics(pid):
    """Retain Linux wait/signal evidence when available; macOS still has ps."""
    fields = {"State", "Pid", "PPid", "NSpgid", "SigPnd", "ShdPnd"}
    try:
        status = (Path("/proc") / str(pid) / "status").read_text()
        return {
            line.split(":", 1)[0]: line.split(":", 1)[1].strip()
            for line in status.splitlines()
            if line.split(":", 1)[0] in fields
        }
    except OSError as error:
        return {"unavailable": type(error).__name__}


def wait_for_terminal_process(pid, pgid, heartbeat, *, timeout=2.0):
    """Require disappearance/Z within a bound and no observed resumed activity.

    SIGKILL is sent to the group by the code under test. It reaps the direct
    worker, not an orphaned grandchild. Host scheduling/reaping is asynchronous;
    D, R, S and T are all nonterminal observations, never successful outcomes.
    """
    last = heartbeat.read_bytes()
    started = time.monotonic()
    history = []
    while True:
        state = process_state(pid)
        elapsed = time.monotonic() - started
        history.append({"seconds": round(elapsed, 3), "process": state})
        assert heartbeat.read_bytes() == last, (
            f"Descendant resumed activity after worker exit: {history!r}"
        )
        if state is not None:
            assert state["pgid"] == pgid, (
                f"Descendant identity/group changed: expected {pgid}, {history!r}"
            )
        if elapsed >= timeout:
            raise AssertionError(
                f"Descendant did not reach terminal state within {timeout}s: "
                f"{history!r}; kernel={kernel_diagnostics(pid)!r}"
            )
        if state is None or state["state"].startswith("Z"):
            return history
        time.sleep(min(0.02, timeout - elapsed))

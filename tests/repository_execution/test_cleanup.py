from execution import test_process as reviewed

from apizr.execution.policy import ExecutionPolicy
from apizr.repository_execution.supervisor import execute

from .helpers import planned


def test_ordinary_descendant_cleanup_reuses_79_regression(
    tmp_path, monkeypatch, request
):
    def invoke(source, payload=None, **policy):
        plan, exposure, sources, _ = planned(
            source.replace("def f(", "def run("),
            policy=ExecutionPolicy.model_validate(policy),
        )
        return execute(plan, exposure, sources, payload or {})

    monkeypatch.setattr(reviewed, "invoke", invoke)
    reviewed.test_ordinary_descendant_is_stopped_with_worker(
        tmp_path, monkeypatch, request
    )


def test_timeout_can_precede_descendant_preparation(tmp_path, monkeypatch, request):
    """Deterministically model a worker not scheduled before its 1200ms budget."""
    import json
    import os
    import signal
    import subprocess
    import sys

    from execution.observation import process_state

    entered = tmp_path / "entered"
    marker = tmp_path / "descendant"
    processes, events = [], []
    popen, killpg = subprocess.Popen, os.killpg

    def stopped(command, *args, **kwargs):
        shim = (
            "import os,signal\nfrom pathlib import Path\n"
            f"Path({str(entered)!r}).write_text('before worker import')\n"
            "os.kill(os.getpid(),signal.SIGSTOP)\n"
            f"os.execv({sys.executable!r},{list(command)!r})\n"
        )
        process = popen([sys.executable, "-I", "-c", shim], *args, **kwargs)
        processes.append(process)
        return process

    def observed(pid, sig):
        # Test-only observation before sending the real signal.
        events.append(
            {
                "call": "killpg",
                "pid": pid,
                "signal": int(sig),
                "process": process_state(pid),
            }
        )
        return killpg(pid, sig)

    plan, exposure, sources, _ = planned(
        f"from pathlib import Path\ndef run():\n Path({str(marker)!r}).touch()\n return 1\n",
        policy=ExecutionPolicy.model_validate({"limits": {"wall_time_ms": 1200}}),
    )
    with monkeypatch.context() as patch:
        # Patch only worker creation; observation's ps must remain a real ps.
        from types import SimpleNamespace

        import apizr.execution.supervisor as supervisor

        patch.setattr(
            supervisor,
            "subprocess",
            SimpleNamespace(
                Popen=stopped,
                PIPE=subprocess.PIPE,
                DEVNULL=subprocess.DEVNULL,
                TimeoutExpired=subprocess.TimeoutExpired,
            ),
        )
        patch.setattr(os, "killpg", observed)
        result = execute(plan, exposure, sources, {})
    assert result.status == "timeout", result
    assert entered.read_text() == "before worker import"
    assert not marker.exists()
    assert events[0]["process"]["state"].startswith("T")
    for process in processes:
        assert process.returncode == -signal.SIGKILL
        assert process.stdin.closed and process.stdout.closed
    request.node.user_properties.append(
        ("startup_trace", json.dumps({"result": result.status, "events": events}))
    )
    # The production deadline still covers startup; the next invocation works.
    assert execute(plan, exposure, sources, {}).value == 1

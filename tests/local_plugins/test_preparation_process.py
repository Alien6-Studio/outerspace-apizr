"""Real process boundaries: bounded output, deadlines and descendant cleanup."""

import json
import os
import signal
import subprocess
import sys
import threading
import time

import pytest

from apizr.extension_runtime.errors import CleanupFailed
from apizr.plugins.preparation import process
from apizr.plugins.preparation.models import Control, PreparationError

pytestmark = pytest.mark.timeout(15)


def invoke(program, tmp_path, *, seconds=5, cancel=None, **options):
    return process.run(
        [sys.executable, "-I", "-S", "-u", "-c", program],
        tmp_path,
        Control(time.monotonic() + seconds, cancel),
        **options,
    )


def test_process_has_only_explicit_environment_and_captures_both_streams(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SECRET_PREPARATION_TOKEN", "do-not-inherit")
    result = invoke(
        "import os,sys,json;print(json.dumps(dict(os.environ)));print('diagnostic',file=sys.stderr);sys.exit(9)",
        tmp_path,
        environment={"EXPLICIT_VALUE": "yes"},
    )
    assert result.code == 9 and result.stderr == b"diagnostic\n"
    environment = json.loads(result.stdout)
    assert environment["EXPLICIT_VALUE"] == "yes"
    assert "SECRET_PREPARATION_TOKEN" not in environment


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_process_output_is_bounded_even_when_child_does_not_exit(tmp_path, stream):
    with pytest.raises(PreparationError, match="resolver_output_too_large"):
        invoke(
            f"import sys,time;sys.{stream}.write('x'*70000);sys.{stream}.flush();time.sleep(10)",
            tmp_path,
            max_stdout=100,
        )


def test_deadline_covers_child_without_open_pipes(tmp_path):
    with pytest.raises(PreparationError, match="preparation_timeout"):
        invoke(
            "import os,time;os.close(1);os.close(2);time.sleep(10)",
            tmp_path,
            seconds=0.15,
        )


@pytest.mark.parametrize("parent_exits", [False, True])
def test_cancel_or_parent_exit_terminates_descendants(tmp_path, parent_exits):
    cancelled = threading.Event()
    pidfile = tmp_path / "descendant"
    program = """import os,time
pid=os.fork()
if pid == 0:
    open('descendant','w').write(str(os.getpid()))
    time.sleep(10)
else:
    time.sleep(.1)
    EXIT
""".replace("EXIT", "os._exit(0)" if parent_exits else "time.sleep(10)")

    def cancel_when_running():
        for _ in range(200):
            if pidfile.exists():
                cancelled.set()
                return
            time.sleep(0.01)

    thread = threading.Thread(target=cancel_when_running)
    if not parent_exits:
        thread.start()
    try:
        if parent_exits:
            assert invoke(program, tmp_path).code == 0
        else:
            with pytest.raises(PreparationError, match="preparation_cancelled"):
                invoke(program, tmp_path, cancel=cancelled)
    finally:
        if thread.ident is not None:
            thread.join(3)
    pid = int(pidfile.read_text())
    try:
        for _ in range(100):
            status = subprocess.run(
                ["ps", "-p", str(pid), "-o", "stat="],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if status.returncode or status.stdout.strip().startswith("Z"):
                break
            time.sleep(0.01)
        else:
            pytest.fail("Preparation left a running descendant")
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_unavailable_tool_is_redacted(tmp_path):
    with pytest.raises(PreparationError, match="^preparation_tool_unavailable$"):
        process.run(
            [str(tmp_path / "secret-tool")], tmp_path, Control(time.monotonic() + 2)
        )


def test_cleanup_failure_is_not_reported_as_success(tmp_path, monkeypatch):
    real_cleanup = process.cleanup_process

    def failed(*args, **kwargs):
        real_cleanup(*args, **kwargs)
        raise CleanupFailed()

    monkeypatch.setattr(process, "cleanup_process", failed)
    with pytest.raises(PreparationError, match="preparation_cleanup_failed"):
        invoke("print('finished')", tmp_path)

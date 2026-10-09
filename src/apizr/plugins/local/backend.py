"""An explicit offline uv backend. No fallback, inherited configuration or logs."""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from apizr.extension_runtime.errors import CleanupFailed
from apizr.extension_runtime.supervisor import cleanup_process

from .control import InstallControl
from .models import PluginError


def require_uv() -> str:
    executable = shutil.which("uv")
    if executable is None:
        raise PluginError("uv_not_found")
    return str(Path(executable).absolute())


def run_uv(
    executable: str,
    arguments: list[str],
    work: Path,
    *,
    control: InstallControl | None = None,
) -> None:
    """The installer is trusted; discard diagnostics and bound its lifetime."""
    try:
        if control is not None:
            control.check()
        process = subprocess.Popen(
            [
                executable,
                "--offline",
                "--no-config",
                "--no-cache",
                "--no-progress",
                *arguments,
            ],
            cwd=work,
            env={
                "HOME": str(work),
                "TMPDIR": str(work),
                "UV_PYTHON_DOWNLOADS": "never",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        try:
            if control is None:
                code = process.wait(timeout=120)
            else:
                command_deadline = min(control.deadline, time.monotonic() + 120)
                while True:
                    remaining = min(
                        control.remaining(), command_deadline - time.monotonic()
                    )
                    if remaining <= 0:
                        raise PluginError("uv_timeout")
                    try:
                        code = process.wait(timeout=min(0.05, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        continue
                control.check()
            if code != 0:
                raise PluginError("uv_install_failed")
        finally:
            if control is not None:
                try:
                    cleanup_process(process, 2000)
                except CleanupFailed:
                    raise PluginError("installation_cleanup_failed") from None
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        raise PluginError("uv_timeout") from None
    except OSError:
        raise PluginError("uv_unavailable") from None

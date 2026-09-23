"""An explicit offline uv backend. No fallback, inherited configuration or logs."""

import os
import shutil
import signal
import subprocess
from pathlib import Path

from .models import PluginError


def require_uv() -> str:
    executable = shutil.which("uv")
    if executable is None:
        raise PluginError("uv_not_found")
    return str(Path(executable).absolute())


def run_uv(executable: str, arguments: list[str], work: Path) -> None:
    """The installer is trusted; discard diagnostics and bound its lifetime."""
    try:
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
            if process.wait(timeout=120) != 0:
                raise PluginError("uv_install_failed")
        finally:
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

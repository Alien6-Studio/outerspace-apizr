"""Fixed stdlib-only identity probe of an explicitly recorded interpreter."""

import json
import subprocess
import time
from pathlib import Path

from apizr.extension_runtime import (
    CleanupFailed,
    ExtensionError,
    InvocationCancelled,
    InvocationTimeout,
    Limits,
)
from apizr.extension_runtime.supervisor import (
    cleanup_process,
    exchange_process,
    signal_process_group,
)
from apizr.local_plugins.activation import _interpreter
from apizr.local_plugins.control import (
    InstallationCancelled,
    InstallationTimeout,
    InstallControl,
)
from apizr.local_plugins.models import Installation, PluginError
from apizr.plugin_lock.models import Target

PROGRAM = """import sys
sys.stdin.buffer.read(1)
import json, platform, sysconfig
print(json.dumps({"implementation": sys.implementation.name,
"python": platform.python_version(), "platform": sysconfig.get_platform(),
"machine": platform.machine(), "abi": str(sysconfig.get_config_var("SOABI") or "")}))
"""
LIMITS = Limits(
    wall_time_ms=10000,
    max_request_bytes=1,
    max_stdout_bytes=8192,
    max_stderr_bytes=8192,
    cleanup_time_ms=2000,
)


def verify_interpreter(
    record: Installation,
    root: Path,
    target: Target,
    work: Path,
    control: InstallControl,
) -> None:
    control.check()
    try:
        _interpreter(record, root)
        process = subprocess.Popen(
            [record.python, "-I", "-S", "-B", "-u", "-c", PROGRAM],
            cwd=work,
            env={},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            close_fds=True,
            bufsize=0,
        )
        signalled = False

        def signal_group() -> None:
            nonlocal signalled
            signal_process_group(process)
            signalled = True

        try:
            raw = exchange_process(
                process,
                b"\n",
                LIMITS,
                min(control.deadline, time.monotonic() + 10),
                control.cancel,
                signal_group,
            )
        finally:
            cleanup_process(process, 2000, group_signalled=signalled)
        actual = Target.model_validate(json.loads(raw), strict=True)
        if actual != target:
            raise PluginError("installed_target_mismatch")
        control.check()
    except InvocationCancelled:
        raise InstallationCancelled() from None
    except InvocationTimeout:
        if time.monotonic() >= control.deadline:
            raise InstallationTimeout() from None
        raise PluginError("interpreter_probe_timeout") from None
    except CleanupFailed:
        raise PluginError("installation_cleanup_failed") from None
    except (OSError, ValueError, ExtensionError):
        raise PluginError("installed_interpreter_unavailable") from None

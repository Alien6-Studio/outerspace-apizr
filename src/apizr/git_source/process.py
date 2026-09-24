"""Bounded Git processes with an explicit environment and one total deadline."""

import os
import selectors
import signal
import stat
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryFile
from threading import Event

from .models import AcquisitionLimits, GitSourceError


class GitRunner:
    def __init__(
        self,
        executable: str,
        work: Path,
        limits: AcquisitionLimits,
        cancel: Event | None,
        ca_file: Path | None,
    ) -> None:
        self.work = work
        self.limits = limits
        self.cancel = cancel
        self.deadline = time.monotonic() + limits.total_timeout_ms / 1000
        self.command = [executable]
        for setting in (
            "core.hooksPath=/dev/null",
            "credential.helper=",
            "credential.interactive=false",
            "protocol.allow=never",
            "protocol.https.allow=always",
            "http.sslVerify=true",
            "http.followRedirects=false",
            "http.proxy=",
            "fetch.recurseSubmodules=false",
            "fetch.unpackLimit=0",
            "transfer.fsckObjects=true",
            "fetch.fsckObjects=true",
            "gc.auto=0",
            "maintenance.auto=false",
        ):
            self.command.extend(("-c", setting))
        if ca_file is not None:
            self.command.extend(("-c", f"http.sslCAInfo={ca_file.resolve()}"))
        self.environment = {
            "PATH": os.defpath,
            "HOME": str(work),
            "XDG_CONFIG_HOME": str(work),
            "TMPDIR": str(work),
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            # Git excludes CWD itself when considering ceiling entries.
            # Stop at the parent of our private CWD, before ancestor discovery.
            "GIT_CEILING_DIRECTORIES": str(work.parent),
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "GIT_ALLOW_PROTOCOL": "https",
            "GIT_NO_REPLACE_OBJECTS": "1",
        }

    def check(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise GitSourceError("git_cancelled")
        if time.monotonic() >= self.deadline:
            raise GitSourceError("git_timeout")

    def check_volume(self) -> None:
        """Observed disk bytes, not a network quota; overshoot is possible."""
        total = entries = 0
        pending = [self.work]
        while pending:
            self.check()
            with os.scandir(pending.pop()) as children:
                for child in children:
                    self.check()
                    entries += 1
                    if entries > self.limits.max_files * 4 + 100:
                        raise GitSourceError("git_acquisition_limit")
                    try:
                        info = child.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue  # Git atomically renames its own lock/pack files.
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(Path(child.path))
                    else:
                        total += info.st_size
                    if total > self.limits.max_acquisition_bytes:
                        raise GitSourceError("git_acquisition_limit")

    def run(
        self, arguments: list[str], *, payload: bytes = b"", output_limit: int = 4194304
    ) -> bytes:
        self.check()
        maximum = min(output_limit, self.limits.max_stdout_bytes)
        with TemporaryFile(dir=self.work) as incoming:
            incoming.write(payload)
            incoming.seek(0)
            try:
                process = subprocess.Popen(
                    [*self.command, *arguments],
                    cwd=self.work,
                    env=self.environment,
                    stdin=incoming,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                    close_fds=True,
                    bufsize=0,
                )
            except OSError:
                raise GitSourceError("git_unavailable") from None
            assert process.stdout is not None and process.stderr is not None
            signalled = False
            received = bytearray()
            errors = 0

            def signal_group() -> None:
                nonlocal signalled
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                signalled = True

            try:
                with selectors.DefaultSelector() as selector:
                    for stream in (process.stdout, process.stderr):
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ)
                    while selector.get_map() or process.poll() is None:
                        self.check_volume()
                        if process.poll() is not None and not signalled:
                            signal_group()
                        for key, _ in selector.select(0.02):
                            is_output = key.fileobj is process.stdout
                            remaining = (
                                maximum - len(received)
                                if is_output
                                else self.limits.max_stderr_bytes - errors
                            )
                            chunk = os.read(key.fd, min(65536, remaining + 1))
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            if len(chunk) > remaining:
                                raise GitSourceError("git_output_limit")
                            if is_output:
                                received.extend(chunk)
                            else:
                                errors += len(chunk)
                self.check_volume()
                if process.returncode:
                    raise GitSourceError("git_command_failed")
                return bytes(received)
            finally:
                failed = False
                cleanup_deadline = time.monotonic() + 2
                try:
                    if not signalled:
                        try:
                            signal_group()
                        except PermissionError:
                            # macOS can reject a signal to an unreaped zombie.
                            # Reap our direct child, then confirm the group signal;
                            # its exit alone never confirms descendant cleanup.
                            if process.poll() is None:
                                process.kill()
                            process.wait(
                                timeout=max(0, cleanup_deadline - time.monotonic())
                            )
                            signal_group()
                except (OSError, subprocess.TimeoutExpired):
                    failed = True
                try:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=max(0, cleanup_deadline - time.monotonic()))
                except (OSError, subprocess.TimeoutExpired):
                    failed = True
                finally:
                    process.stdout.close()
                    process.stderr.close()
                if failed:
                    raise GitSourceError("git_cleanup_failed") from None

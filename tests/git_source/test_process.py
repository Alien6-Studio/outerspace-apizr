import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from apizr.git_source import AcquisitionLimits, GitSourceError, acquire_snapshot

from .conftest import git_fixture, https

pytestmark = pytest.mark.timeout(20)


@pytest.mark.parametrize("response", ["repository", "redirect", "unauthorized"])
def test_no_implicit_credentials_or_redirects(
    tmp_path, tls, scratch, monkeypatch, response
):

    git_fixture.repository(tmp_path)
    requests = []
    backend = git_fixture.handler(tmp_path)

    class Handler(backend):
        def respond(self):
            requests.append(dict(self.headers))
            if response == "repository":
                super().respond()
            else:
                self.send_response(302 if response == "redirect" else 401)
                self.send_header("Location", "http://localhost:1/forbidden")
                self.send_header("WWW-Authenticate", 'Basic realm="fixture"')
                self.end_headers()

    marker = tmp_path / "credential-helper"
    monkeypatch.setenv("GIT_CONFIG_COUNT", "2")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "http.extraHeader")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "Authorization: Bearer SECRET")
    monkeypatch.setenv("GIT_CONFIG_KEY_1", "credential.helper")
    monkeypatch.setenv("GIT_CONFIG_VALUE_1", f"!touch {marker}")
    with https.https_server(*tls, Handler) as url:
        if response == "repository":
            with acquire_snapshot(url + "/repo.git", "main", ca_file=tls[0]):
                pass
        else:
            with pytest.raises(GitSourceError, match="git_command_failed"):
                with acquire_snapshot(url + "/repo.git", "main", ca_file=tls[0]):
                    pytest.fail("accepted")
    assert requests and all(
        "Authorization" not in headers and "Cookie" not in headers
        for headers in requests
    )
    assert not marker.exists()


@pytest.mark.parametrize("kind", ["timeout", "cancel"])
def test_blocked_https_bounded_and_clean(remote, tls, scratch, kind):
    from http.server import BaseHTTPRequestHandler

    started, release, cancel = threading.Event(), threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            started.set()
            release.wait(5)

    with https.https_server(*tls, Handler) as url:

        def acquire():
            with acquire_snapshot(
                url + "/repo.git",
                "main",
                ca_file=tls[0],
                cancel=cancel,
                limits=AcquisitionLimits(
                    total_timeout_ms=500 if kind == "timeout" else 4000
                ),
            ):
                pytest.fail("accepted")

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(acquire)
            try:
                assert started.wait(3)
                if kind == "cancel":
                    cancel.set()
                with pytest.raises(
                    GitSourceError,
                    match="git_timeout" if kind == "timeout" else "git_cancelled",
                ):
                    future.result(timeout=5)
            finally:
                release.set()
    assert not list(scratch.iterdir())
    with acquire_snapshot(remote[0], "main", ca_file=tls[0]):
        pass


@pytest.mark.parametrize("kind", ["stdout", "stderr", "disk", "child"])
def test_live_process_limits_close_streams_and_reap(
    tmp_path, scratch, monkeypatch, kind
):
    from apizr.git_source.process import GitRunner

    wrapper = tmp_path / "git-wrapper"
    marker = tmp_path / "pid"
    if kind == "child":
        action = "import subprocess\np=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n"
        action += f"open({str(marker)!r},'w').write(str(p.pid))\n"
    elif kind == "disk":
        action = "with open('growing','wb',buffering=0) as f:\n while True: f.write(b'x'*65536)\n"
    else:
        fd = 1 if kind == "stdout" else 2
        action = f"while True: os.write({fd},b'x'*65536)\n"
    wrapper.write_text(f"#!{sys.executable}\nimport os,sys\n{action}")
    wrapper.chmod(0o700)
    processes = []
    original = subprocess.Popen

    def capture(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", capture)
    work = scratch / "runner"
    work.mkdir()
    runner = GitRunner(
        str(wrapper),
        work,
        AcquisitionLimits(
            total_timeout_ms=2000,
            max_stdout_bytes=1024,
            max_stderr_bytes=1024,
            max_acquisition_bytes=1048576,
        ),
        None,
        None,
    )
    try:
        if kind == "child":
            assert runner.run([]) == b""
            pid = int(marker.read_text())
            # A killed orphan may remain as a zombie until the host reaps it.
            state = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout.strip()
            assert not state or state.startswith("Z")
        else:
            with pytest.raises(
                GitSourceError,
                match="git_acquisition_limit" if kind == "disk" else "git_output_limit",
            ):
                runner.run([])
        process = processes[0]
        assert process.poll() is not None
        assert process.stdout.closed and process.stderr.closed
        with pytest.raises(ChildProcessError):
            os.waitpid(process.pid, os.WNOHANG)
    finally:
        import shutil

        shutil.rmtree(work)


def test_keyboard_interrupt_kills_acquisition_child(tmp_path, scratch, monkeypatch):
    from apizr.git_source.process import GitRunner

    wrapper = tmp_path / "git"
    marker = tmp_path / "started"
    wrapper.write_text(
        f"#!{sys.executable}\nimport time\nopen({str(marker)!r},'w').close()\ntime.sleep(30)\n"
    )
    wrapper.chmod(0o700)
    monkeypatch.setattr("shutil.which", lambda _: str(wrapper))
    original = GitRunner.check

    def interrupt(self):
        original(self)
        if marker.exists():
            raise KeyboardInterrupt

    monkeypatch.setattr(GitRunner, "check", interrupt)
    with pytest.raises(KeyboardInterrupt):
        with acquire_snapshot("https://example.com/a", "main"):
            pytest.fail("accepted")
    assert not list(scratch.iterdir())

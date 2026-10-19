"""Real smart-HTTPS Git fixture, shared by tests and the installed-wheel proof."""

import os
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit


def git(directory: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    assert executable is not None
    return subprocess.check_output(
        [executable, *arguments],
        cwd=directory,
        env={
            "PATH": os.defpath,
            "HOME": str(directory),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        },
        stderr=subprocess.PIPE,
        timeout=10,
        text=True,
    ).strip()


def repository(directory: Path) -> tuple[Path, str]:
    source = directory / "repo.git"
    source.mkdir()
    git(source, "init", "--initial-branch=main")
    (source / "service").mkdir()
    (source / "service" / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n"
    )
    git(source, "add", ".")
    git(source, "commit", "-m", "fixture")
    commit = git(source, "rev-parse", "HEAD")
    git(source, "tag", "v1")
    git(source, "tag", "-a", "annotated", "-m", "tag fixture")
    return source, commit


def handler(directory: Path) -> type[BaseHTTPRequestHandler]:
    executable = shutil.which("git")
    assert executable is not None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.respond()

        def do_POST(self) -> None:
            self.respond()

        def respond(self) -> None:
            parsed = urlsplit(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1048576:
                self.send_error(413)
                return
            self.connection.settimeout(5)
            incoming = self.rfile.read(length)
            output = subprocess.run(
                [executable, "http-backend"],
                input=incoming,
                capture_output=True,
                timeout=10,
                env={
                    "PATH": os.defpath,
                    "GIT_PROJECT_ROOT": str(directory),
                    "GIT_HTTP_EXPORT_ALL": "1",
                    "PATH_INFO": parsed.path,
                    "REQUEST_METHOD": self.command,
                    "QUERY_STRING": parsed.query,
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": str(length),
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "HOME": str(directory),
                },
            ).stdout
            headers, body = output.split(b"\r\n\r\n", 1)
            pairs = [
                line.decode("ascii").split(":", 1) for line in headers.split(b"\r\n")
            ]
            status = next(
                (int(v.strip().split()[0]) for k, v in pairs if k == "Status"), 200
            )
            self.send_response(status)
            for name, value in pairs:
                if name != "Status":
                    self.send_header(name, value.strip())
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def trusted_git(directory: Path, ca_file: Path) -> Path:
    """Test-only installed Git wrapper explicitly trusts the fixture's CA."""
    executable = shutil.which("git")
    assert executable is not None
    directory.mkdir()
    wrapper = directory / "git"
    wrapper.write_text(
        f"#!{sys.executable}\nimport os,sys\n"
        f"os.execv({executable!r}, [{executable!r}, '-c', "
        f"{'http.sslCAInfo=' + str(ca_file)!r}, *sys.argv[1:]])\n"
    )
    wrapper.chmod(0o700)
    return directory

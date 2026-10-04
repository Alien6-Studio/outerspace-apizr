"""Real TLS responses exercise the fallback, separately from registry qualification."""

import base64
import json
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from threading import Event

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from apizr_oci.absence import main as absence_main
from apizr_oci.model import BuildError, PushRequest
from apizr_oci.native import run as native_run
from apizr_oci.process import run
from apizr_oci.push import authentication
from https_fixture import certificate, https_server

ABSENT = b'{"errors":[{"code":"MANIFEST_UNKNOWN","message":"manifest unknown","detail":{"tag":"first"}}]}'


@pytest.fixture
def registry(tmp_path):
    cert, key = certificate(tmp_path)
    calls = []
    response = {"status": 404, "body": ABSENT}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append((self.path, self.headers.get("Authorization")))
            self.send_response(response["status"])
            self.send_header("Location", "/must-not-follow")
            self.end_headers()
            self.wfile.write(response["body"])

    with https_server(cert, key, Handler) as url:
        registry = url.removeprefix("https://")
        auth = tmp_path / "auth.json"
        encoded = base64.b64encode(b"user:fixture-password").decode()
        auth.write_text(json.dumps({"auths": {registry: {"auth": encoded}}}))
        executable = tmp_path / "docker"
        executable.write_text(
            "#!"
            + sys.executable
            + '\nimport sys\nsys.stderr.write("manifest unknown: manifest unknown\\n")\nsys.exit(1)\n'
        )
        executable.chmod(0o700)
        request = PushRequest.model_validate(
            {
                "schema": "apizr.oci-push/v1",
                "image_id": "sha256:" + "a" * 64,
                "platform": "linux/amd64",
                "inputs_sha256": "b" * 64,
                "destination": "registry.test/team/service:first",
                "docker": {
                    "executable": str(executable),
                    "socket": str(tmp_path / "socket"),
                },
                "authentication": {"config_file": str(auth), "ca_file": str(cert)},
            }
        )
        # Only this transport fixture bypasses the public ban on localhost.
        request = request.model_copy(
            update={"destination": registry + "/team/service:first"}
        )
        work = tmp_path / "work"
        work.mkdir()
        authentication(request, work)
        yield request, work, response, calls, "Basic " + encoded


def invoke(request, work, **kwargs):
    return run(
        request,
        work,
        ["manifest", "inspect", "--verbose", request.destination],
        time.monotonic() + 5,
        absent_reference=request.destination,
        **kwargs,
    )


def test_exact_authenticated_https_absence_permits_first_push(registry, monkeypatch):
    request, work, response, calls, auth = registry
    assert invoke(request, work) == b"null"
    assert calls == [("/v2/team/service/manifests/first", auth)]
    monkeypatch.chdir(work)
    monkeypatch.setattr(sys, "argv", ["absence.py", request.destination, "5"])
    assert absence_main() == 0
    assert calls == [("/v2/team/service/manifests/first", auth)] * 2


@pytest.mark.parametrize(
    "status,body",
    [
        (200, b"{}"),
        (401, ABSENT),
        (403, ABSENT),
        (500, ABSENT),
        (302, ABSENT),
        (404, b""),
        (404, b"not found"),
        (404, b'{"errors":[{"code":"UNAUTHORIZED","message":"manifest unknown"}]}'),
        (
            404,
            b'{"errors":[],"errors":[{"code":"MANIFEST_UNKNOWN","message":"manifest unknown"}]}',
        ),
        (404, b"x" * 65537),
        (404, b'{"errors":[]}'),
        (
            404,
            b'{"errors":[{"code":"MANIFEST_UNKNOWN","message":"missing"},{"code":"DENIED","message":"no"}]}',
        ),
    ],
    ids=[
        "exists",
        "auth",
        "denied",
        "server",
        "redirect",
        "empty",
        "html",
        "wrong-code",
        "duplicate",
        "oversize",
        "no-errors",
        "multiple-errors",
    ],
)
def test_ambiguous_or_failed_observation_never_means_absent(
    registry, status, body, monkeypatch
):
    request, work, response, calls, _ = registry
    response.update(status=status, body=body)
    with pytest.raises(BuildError):
        invoke(request, work)
    assert len(calls) == 1
    monkeypatch.chdir(work)
    monkeypatch.setattr(sys, "argv", ["absence.py", request.destination, "5"])
    assert absence_main() == 1
    assert len(calls) == 2


def test_untrusted_tls_cancel_and_deadline_refuse(registry):
    request, work, _, calls, _ = registry
    (work / "registry-ca.pem").unlink()
    with pytest.raises(BuildError):
        invoke(request, work)
    assert calls == []
    cancel = Event()
    cancel.set()
    with pytest.raises(BuildError, match="cancelled"):
        invoke(request, work, cancel=cancel)
    with pytest.raises(BuildError, match="timeout"):
        native_run(
            Path(sys.executable),
            ["-c", "import time;time.sleep(30)"],
            work,
            time.monotonic() + 0.05,
            4096,
        )
    with pytest.raises(BuildError, match="cancelled"):
        native_run(
            Path(sys.executable),
            ["-c", "pass"],
            work,
            time.monotonic() + 1,
            4096,
            cancel=cancel,
        )


def test_fallback_not_used_for_other_reference_or_command(registry):
    request, work, _, calls, _ = registry
    with pytest.raises(BuildError):
        run(
            request,
            work,
            ["manifest", "inspect", "--verbose", request.destination + "2"],
            time.monotonic() + 2,
            absent_reference=request.destination + "2",
        )
    assert calls == []

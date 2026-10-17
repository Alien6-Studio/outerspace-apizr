"""The private collector can consume public fixtures without contacting production."""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scripts.qualification.interfaces import telemetry_conformance as conformance
from scripts.qualification.interfaces.telemetry_contract import make_server


@pytest.fixture
def receiver():
    with make_server() as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()


def test_public_suite_qualifies_real_stub_and_emits_only_synthetic_aggregate(receiver):
    report = conformance.qualify(receiver)
    assert report["result"] == "passed"
    assert len(report["checks"]) == 45
    assert all(row["result"] == "passed" for row in report["checks"])
    assert sum(row["count"] for row in report["expected_synthetic_counts"]) == 1002
    assert report["production_qualified"] is False
    assert report["private_storage_and_retention_qualified"] is False
    serialized = json.dumps(report)
    for excluded in (receiver, "sensitive/path", "arbitrary_secret", '"body":'):
        assert excluded not in serialized


@pytest.mark.parametrize(
    "value",
    [
        "https://telemetry.outerspace.sh",
        "http://localhost:8080",
        "http://192.0.2.1:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://user@127.0.0.1:8080",
        "http://127.0.0.1:8080/path",
        "http://127.0.0.1:8080/?x=1",
        "http://127.0.0.1:8080/#x",
        "",
        "http://[invalid",
        "http://127.0.0.1:8080/\n",
    ],
)
def test_production_dns_credentials_and_unsafe_endpoints_refused_before_io(
    value, monkeypatch
):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: pytest.fail("network attempt")
    )
    monkeypatch.setattr(
        conformance.Path, "read_bytes", lambda *a: pytest.fail("fixture read")
    )
    with pytest.raises(ValueError, match="explicit HTTP loopback"):
        conformance.qualify(value)


def test_nonempty_receiver_responses_are_rejected_without_retaining_them():
    secret = b"unapproved-collector-response"

    class RespondsWithBody(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            self.send_response(204)
            self.send_header("Content-Length", str(len(secret)))
            self.end_headers()
            self.wfile.write(secret)

    with HTTPServer(("127.0.0.1", 0), RespondsWithBody) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            report = conformance.qualify(f"http://127.0.0.1:{server.server_port}")
        finally:
            server.shutdown()
            thread.join(timeout=5)
    assert report["result"] == "failed"
    assert secret.decode() not in json.dumps(report)
    assert all(row.get("reason") == "nonempty_response" for row in report["checks"])


def test_closed_local_port_is_a_failed_qualification_not_an_approval():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    report = conformance.qualify(f"http://127.0.0.1:{port}", timeout=0.1)
    assert report["result"] == "failed"
    assert all(row["reason"] == "transport_failure" for row in report["checks"])

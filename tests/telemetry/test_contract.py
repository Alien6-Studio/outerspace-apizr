"""Public synthetic fixtures, closed schema, bounds and exact CLI/stub parity."""

import importlib.util
import json
import socket
import subprocess
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator

from apizr import cli
from apizr.telemetry import (
    UsageEvent,
    UsageReport,
    decode_report,
    preview,
    report_bytes,
)
from apizr.telemetry.model import MAX_REPORT_BYTES

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = json.loads((ROOT / "tests/fixtures/telemetry/conformance.json").read_bytes())
SPEC = importlib.util.spec_from_file_location(
    "telemetry_conformance",
    ROOT / "scripts/qualification/interfaces/telemetry_contract.py",
)
STUB = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STUB)


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda item: item["name"])
def test_reusable_contract_fixtures(fixture):
    raw = fixture["body"].encode()
    if fixture["accepted"]:
        report = decode_report(raw)
        assert decode_report(report_bytes(report)) == report
    else:
        with pytest.raises(ValueError, match="^invalid_telemetry_report$"):
            decode_report(raw)


def test_byte_boundary_encoding_and_forged_models():
    raw = FIXTURES[0]["body"].encode()
    boundary = raw + b" " * (16384 - len(raw))
    assert decode_report(boundary).events == ()
    with pytest.raises(ValueError, match="invalid_telemetry_report"):
        decode_report(boundary + b" ")
    with pytest.raises(ValueError, match="invalid_telemetry_report"):
        decode_report(b"\xff")
    report = decode_report(raw)
    with pytest.raises(ValueError, match="invalid_telemetry_report"):
        report_bytes(report.model_copy(update={"context": "secret"}))
    with pytest.raises(ValueError, match="invalid_telemetry_report"):
        report_bytes(
            report.model_copy(
                update={
                    "events": (
                        UsageEvent.model_construct(
                            operation="secret", outcome="success", count=1
                        ),
                    )
                }
            )
        )
    with pytest.raises(ValueError):
        report.context = "sdk"


def test_public_schema_export_and_acceptance():
    path = ROOT / "docs/specs/apizr-telemetry-v1.schema.json"
    before = path.read_bytes()
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/qualification/interfaces/telemetry_contract.py"),
            "--export-schema",
        ],
        check=True,
    )
    assert path.read_bytes() == before
    schema = json.loads(before)
    assert schema == UsageReport.model_json_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for item in FIXTURES:
        if item["accepted"]:
            validator.validate(json.loads(item["body"]))
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["UsageEvent"]["additionalProperties"] is False


@pytest.fixture
def receiver():
    with STUB.make_server() as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()


def post(server, body, *, path="/", headers=None):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    connection.request(
        "POST", path, body=body, headers=headers or {"Content-Type": "application/json"}
    )
    response = connection.getresponse()
    result = response.status, response.read()
    connection.close()
    return result


def test_real_stub_acceptance_rejection_and_no_retention(
    receiver, tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    for item in FIXTURES:
        status, body = post(receiver, item["body"].encode())
        assert status == (204 if item["accepted"] else 400), item["name"]
        assert body == b""
    assert post(receiver, b"x" * (MAX_REPORT_BYTES + 1)) == (413, b"")
    assert post(receiver, b"") == (413, b"")
    assert post(receiver, b"{}", path="/secret") == (400, b"")
    assert post(receiver, b"{}", headers={"Content-Type": "text/plain"}) == (400, b"")
    assert post(receiver, b"{}", headers={"Transfer-Encoding": "chunked"}) == (400, b"")
    for lengths in ([], ["2", "2"], ["-1"], ["2x"], ["999999999999999999999999"]):
        connection = HTTPConnection("127.0.0.1", receiver.server_port, timeout=5)
        connection.putrequest("POST", "/")
        connection.putheader("Content-Type", "application/json")
        for value in lengths:
            connection.putheader("Content-Length", value)
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == (
            413 if lengths == ["999999999999999999999999"] else 400
        )
        assert response.read() == b""
        connection.close()
    connection = socket.create_connection(("127.0.0.1", receiver.server_port))
    connection.sendall(
        b"POST / HTTP/1.0\r\nContent-Type: application/json\r\nContent-Length: 9\r\n\r\n{}"
    )
    connection.shutdown(socket.SHUT_WR)
    assert b"400" in connection.recv(1024)
    connection.close()
    assert list(tmp_path.iterdir()) == []
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("opt_in", [False, True])
def test_cli_exact_preview_against_stub(receiver, monkeypatch, opt_in):
    endpoint = f"http://127.0.0.1:{receiver.server_port}"
    env = {"APIZR_TELEMETRY_TEST_ENDPOINT": endpoint}
    if opt_in:
        env["APIZR_TELEMETRY"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "apizr.cli", "telemetry", "preview"],
        env={"PATH": str(Path(sys.executable).parent), **env},
        capture_output=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["endpoint"] == endpoint
    assert report["opt_in_requested"] is opt_in
    assert report["collection_enabled"] is False
    assert report["transmission_available"] is False
    assert post(receiver, report["payload"].encode()) == (204, b"")


@pytest.mark.parametrize("opt_in", [False, True])
def test_preview_and_status_never_touch_network_or_project(
    monkeypatch, capsys, tmp_path, opt_in
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **kw: pytest.fail("DNS attempt")
    )
    monkeypatch.setattr(
        socket, "socket", lambda *a, **kw: pytest.fail("socket attempt")
    )
    monkeypatch.setattr(Path, "open", lambda *a, **kw: pytest.fail("filesystem access"))
    monkeypatch.setenv("APIZR_TELEMETRY", "1" if opt_in else "0")
    monkeypatch.delenv("APIZR_TELEMETRY_TEST_ENDPOINT", raising=False)
    assert cli.main(["telemetry", "preview"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["endpoint"] == "https://telemetry.outerspace.sh"
    assert result["opt_in_requested"] is opt_in
    assert result["transmission_available"] is False
    assert decode_report(result["payload"].encode()).events == ()
    assert cli.main(["telemetry", "status"]) == 0
    assert "payload" not in json.loads(capsys.readouterr().out)
    for context in ("cli", "sdk", "vscode"):
        assert preview(context=context)["collection_enabled"] is False
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "env,allowed",
    [
        ({}, True),
        ({"CI": "true"}, False),
        ({"CI": "1"}, False),
        ({"CI": "false"}, True),
        ({"CI": "0"}, True),
        ({"APIZR_TELEMETRY_ALLOWED": "0"}, False),
        ({"APIZR_TELEMETRY_ALLOWED": "arbitrary"}, False),
    ],
)
def test_stricter_context_restriction_wins(env, allowed):
    result = preview(environ={**env, "APIZR_TELEMETRY": "1"})
    assert result["context_allows"] is allowed
    assert result["collection_enabled"] is False
    assert result["transmission_available"] is False


@pytest.mark.parametrize("opt_in", ["0", "1"])
def test_fresh_import_and_cli_preview_never_attempt_network(tmp_path, opt_in):
    code = """
import os
import sys

os.environ["APIZR_TELEMETRY"] = sys.argv[1]
os.environ.pop("APIZR_TELEMETRY_TEST_ENDPOINT", None)

def guard(event, args):
    if event.startswith("socket."):
        raise AssertionError("network attempt")

sys.addaudithook(guard)
from apizr.telemetry import preview
from apizr.cli import main
assert preview(context="sdk")["transmission_available"] is False
assert main(["telemetry", "preview"]) == 0
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, opt_in],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout)["collection_enabled"] is False
    assert result.stderr == b""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "endpoint",
    ["http://127.0.0.1:1234", "http://[::1]:1234/", "http://127.12.34.56:4567/"],
)
def test_loopback_test_override_without_dns(endpoint):
    with patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS")):
        assert (
            preview(environ={"APIZR_TELEMETRY_TEST_ENDPOINT": endpoint})["endpoint"]
            == endpoint
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com",
        "http://localhost:1234",
        "http://192.0.2.1:1234",
        "https://127.0.0.1:1234",
        "http://127.0.0.1",
        "http://127.0.0.1:0",
        "http://127.0.0.1:65536",
        "http://user@127.0.0.1:1234",
        "http://user:pass@127.0.0.1:1234",
        "http://127.0.0.1:1234/path",
        "http://127.0.0.1:1234/?query=secret",
        "http://127.0.0.1:1234/#secret",
        "http://127.0.0.1:1234/" + "a" * 128,
        "http://[bad",
        "",
        "http://:1234",
        "http://127.0.0.1:1234/\n",
        " http://127.0.0.1:1234",
        "http://127.0.0.1:1234/\u2028",
    ],
)
def test_external_or_unsafe_override_refused(endpoint, monkeypatch, capsys):
    with pytest.raises(ValueError, match="^invalid_telemetry_test_endpoint$"):
        preview(environ={"APIZR_TELEMETRY_TEST_ENDPOINT": endpoint})
    monkeypatch.setenv("APIZR_TELEMETRY_TEST_ENDPOINT", endpoint)
    assert cli.main(["telemetry", "preview"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "apizr: invalid_telemetry_test_endpoint\n"

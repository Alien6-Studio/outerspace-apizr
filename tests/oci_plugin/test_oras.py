"""Pinned ORAS contracts and bounded native reads, without registry side effects."""

import hashlib
import json
import sys
import time
from pathlib import Path

import pytest
from apizr_oci import oras
from apizr_oci.model import BuildError
from apizr_oci.native import run

REF = "registry.test:5443/services/rest@sha256:" + "a" * 64


@pytest.fixture
def client(tmp_path, monkeypatch):
    binary = tmp_path / "oras"
    binary.write_bytes(b"pinned native tool")
    binary.chmod(0o700)
    auth = tmp_path / "auth.json"
    auth.write_text('{"auths":{"registry.test:5443":{"auth":"dTpw"}}}')
    transport = oras.Transport.model_validate(
        {
            "tool": {
                "executable": str(binary),
                "version": "1.3.4",
                "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            },
            "authentication": {"config_file": str(auth)},
        }
    )
    monkeypatch.setattr(oras, "run", lambda *args, **kwargs: b"Version: 1.3.4\n")
    work = tmp_path / "work"
    work.mkdir()
    return oras.Registry(transport, REF, work, time.monotonic() + 20)


@pytest.mark.parametrize(
    "fault",
    ["none", "size", "duplicate", "nested", "type", "reference", "urls", "shape"],
)
def test_discovery_contract_and_limits(client, monkeypatch, fault):
    child = {
        "reference": REF,
        "digest": REF.split("@")[1],
        "size": 100,
        "mediaType": oras.OCI_MANIFEST,
        "artifactType": "test",
        "referrers": [],
    }
    value = {"reference": REF, "digest": REF.split("@")[1], "referrers": [child]}
    if fault == "size":
        child["size"] = 1048577
    if fault == "duplicate":
        value["referrers"].append(child)
    if fault == "nested":
        child["referrers"] = [child.copy()]
    if fault == "type":
        child["artifactType"] = "wrong"
    if fault == "reference":
        child["reference"] = REF + "x"
    if fault == "urls":
        child["urls"] = ["http://external"]
    if fault == "shape":
        value = []
    monkeypatch.setattr(
        client, "call", lambda *args, **kwargs: json.dumps(value).encode()
    )
    if fault == "none":
        assert client.discover("test")[0]["verified"] is False
        client.transport = client.transport.model_copy(update={"max_candidates": 0})
        with pytest.raises(BuildError, match="limit"):
            client.discover("test")
    else:
        with pytest.raises(BuildError):
            client.discover("test")


def test_manifest_and_blob_byte_integrity(client, monkeypatch):
    raw = (
        b'{"schemaVersion":2,"mediaType":"application/vnd.oci.image.manifest.v1+json"}'
    )
    monkeypatch.setattr(client, "call", lambda *args, **kwargs: raw)
    ref = client.repository + "@" + oras.sha(raw)
    received, desc = client.manifest(ref)
    assert received == raw and desc["size"] == len(raw)
    assert client.blob(desc) == raw
    for changed in (desc | {"size": 1}, desc | {"digest": "sha256:" + "b" * 64}):
        with pytest.raises(BuildError):
            client.blob(changed)
    with pytest.raises(BuildError):
        client.manifest(REF)
    with pytest.raises(BuildError):
        client.manifest(ref.replace("/services/", "/else/"))
    with pytest.raises(ValueError):
        oras.digest_reference("registry.test/services/rest:tag")


@pytest.mark.parametrize(
    "payload,code",
    [
        ("import time;time.sleep(10)", "native_timeout"),
        ('print("x"*100000)', "native_output_limit"),
        ('import sys;sys.stderr.write("x"*100000)', "native_output_limit"),
        ("raise SystemExit(1)", "native_command_failed"),
    ],
)
def test_native_failure_and_recovery(tmp_path, payload, code):
    deadline = time.monotonic() + (0.3 if code == "native_timeout" else 5)
    with pytest.raises(BuildError, match=code):
        run(
            Path(sys.executable),
            ["-c", payload],
            tmp_path,
            deadline,
            2048,
            stdout_limit=1000,
        )
    assert (
        run(
            Path(sys.executable),
            ["-c", 'print("ok")'],
            tmp_path,
            time.monotonic() + 5,
            2048,
        )
        == b"ok\n"
    )


def test_native_environment_and_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_VALUE", "sensitive")
    assert (
        run(
            Path(sys.executable),
            ["-c", 'import os;assert "SECRET_VALUE" not in os.environ'],
            tmp_path,
            time.monotonic() + 5,
            1024,
        )
        == b""
    )
    with pytest.raises(BuildError):
        run(tmp_path / "missing", [], tmp_path, time.monotonic() + 5, 1024)
    with pytest.raises(BuildError):
        run(Path(sys.executable), [], tmp_path, 0, 1024)


@pytest.mark.parametrize("fault", ["missing", "hash", "version", "api"])
def test_explicit_tool_and_api_refusals(client, tmp_path, monkeypatch, fault):
    assert "--plain-http=false" in client.flags
    transport = client.transport
    if fault == "missing":
        transport = transport.model_copy(
            update={
                "tool": transport.tool.model_copy(
                    update={"executable": str(tmp_path / "absent")}
                )
            }
        )
    if fault == "hash":
        transport = transport.model_copy(
            update={"tool": transport.tool.model_copy(update={"sha256": "f" * 64})}
        )
    if fault == "version":
        monkeypatch.setattr(oras, "run", lambda *args, **kwargs: b"Version: 1.2.0\n")
    if fault == "api":
        monkeypatch.setattr(
            client,
            "call",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                BuildError("native_command_failed")
            ),
        )
        with pytest.raises(BuildError, match="native_command_failed"):
            client.discover("test")
        return
    target = tmp_path / "new-work"
    target.mkdir()
    with pytest.raises(BuildError):
        oras.Registry(transport, REF, target, time.monotonic() + 10)

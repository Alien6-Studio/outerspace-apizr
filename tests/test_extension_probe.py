"""The private packaging experiment never enters production plugin dispatch."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from apizr._prototypes.extension import Request, invoke, main, validate_response

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "packaging_probe", ROOT / "scripts/smoke_extension_packaging.py"
)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def response():
    return {
        "protocol": "apizr.extension-probe/v1",
        "request_id": "packaging-proof",
        "operation": "describe",
        "result": {"source_digest": "abc", "message": "demo extension reached"},
    }


def test_validated_result():
    assert (
        validate_response(
            json.dumps(response()), Request(source_digest="abc")
        ).result.source_digest
        == "abc"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("protocol", "apizr.extension-probe/v2"),
        ("request_id", "other"),
        ("operation", "publish"),
        ("extra", True),
        ("result", {"source_digest": 42, "message": "demo extension reached"}),
    ],
)
def test_incompatible_or_malformed_response(field, value):
    data = response()
    data[field] = value
    with pytest.raises(ValidationError):
        validate_response(json.dumps(data), Request(source_digest="abc"))


def test_invalid_json_and_digest():
    with pytest.raises(ValidationError):
        validate_response("not json", Request(source_digest="abc"))
    with pytest.raises(ValueError, match="digest"):
        validate_response(json.dumps(response()), Request(source_digest="different"))


def test_missing_backend_has_no_side_effects(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("Must not download or execute anything"),
    )
    monkeypatch.setattr(
        sys, "argv", ["probe", "--work-dir", str(tmp_path / "untouched")]
    )
    with pytest.raises(RuntimeError, match="uv is required.*Nothing was downloaded"):
        probe.main()
    assert not (tmp_path / "untouched").exists()


def test_snapshot_detects_bytes_modes_links_additions_and_deletions(tmp_path):
    file = tmp_path / "file"
    file.write_bytes(b"one")
    link = tmp_path / "link"
    link.symlink_to("file")
    baseline = probe.snapshot(tmp_path)
    file.write_bytes(b"two")
    assert probe.snapshot(tmp_path) != baseline
    file.write_bytes(b"one")
    assert probe.snapshot(tmp_path) == baseline
    file.chmod(0o700)
    assert probe.snapshot(tmp_path) != baseline
    file.chmod(0o644)
    link.unlink()
    link.symlink_to("missing")
    assert probe.snapshot(tmp_path) != baseline
    file.unlink()
    assert "file" not in probe.snapshot(tmp_path)
    (tmp_path / "new").mkdir()
    assert "new" in probe.snapshot(tmp_path)


def test_missing_interpreter():
    with pytest.raises(ValueError, match="absolute installed"):
        invoke(Path("relative"), Request(source_digest="abc"))


def test_process_failure_and_timeout(monkeypatch):
    for error in (
        OSError("missing"),
        subprocess.TimeoutExpired("probe", 10),
        subprocess.CalledProcessError(2, "probe"),
    ):

        def fail(*args, error=error, **kwargs):
            raise error

        monkeypatch.setattr(subprocess, "run", fail)
        with pytest.raises(ValueError, match="failed or timed out"):
            invoke(Path(sys.executable), Request(source_digest="abc"))


def test_process_contract(monkeypatch):
    def run(argv, **kwargs):
        assert argv[1:] == ["-I", "-B", "-m", "apizr_extension_probe"]
        assert kwargs["timeout"] == 10
        assert json.loads(kwargs["input"])["source_digest"] == "abc"
        return subprocess.CompletedProcess(argv, 0, json.dumps(response()))

    monkeypatch.setattr(subprocess, "run", run)
    assert (
        invoke(Path(sys.executable), Request(source_digest="abc")).result.message
        == "demo extension reached"
    )


def test_host_main(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["probe", sys.executable])

    def success(python, request):
        data = response()
        data["result"]["source_digest"] = request.source_digest
        return validate_response(json.dumps(data), request)

    monkeypatch.setattr("apizr._prototypes.extension.invoke", success)
    assert main() == 0
    assert (
        json.loads(capsys.readouterr().out)["result"]["message"]
        == "demo extension reached"
    )

    def failure(*args):
        raise ValueError("refused")

    monkeypatch.setattr("apizr._prototypes.extension.invoke", failure)
    assert main() == 2
    assert "refused" in capsys.readouterr().err

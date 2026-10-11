"""External consumers verify retained metadata without importing business code."""

import json
import shutil

import pytest

from apizr.capabilities.model import Digest
from apizr.cli.commands.exposure import main
from apizr.delivery import identity
from apizr.repository.serialization import canonical_bytes
from apizr.repository_interfaces.evidence import (
    export_evidence,
    read_document,
    verify_evidence,
)
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.output import write_bundle


@pytest.mark.parametrize("interface", ["rest", "mcp"])
def test_export_verify_after_removing_business_code(inputs, tmp_path, interface, capfd):
    bundle, output = tmp_path / "bundle", tmp_path / "evidence"
    write_bundle(bundle, render_repository_bundle(*inputs, interface=interface))
    assert (
        main(
            [
                "export",
                "--bundle-dir",
                str(bundle),
                "--output-dir",
                str(output),
                "--interface",
                interface,
            ]
        )
        == 0
    )
    raw = capfd.readouterr().out.encode()
    assert all(p.suffix == ".json" for p in output.iterdir())
    assert (output / f"apizr-repository-{interface}.json").read_bytes() == raw
    shutil.rmtree(bundle)
    assert (
        main(
            [
                "verify",
                "--evidence-dir",
                str(output),
                "--interface",
                interface,
                "--bundle-sha256",
                Digest.of_bytes(raw).value,
            ]
        )
        == 0
    )
    assert capfd.readouterr().out.encode() == raw
    assert (
        main(
            [
                "verify",
                "--evidence-dir",
                str(output),
                "--interface",
                interface,
                "--bundle-sha256",
                "0" * 64,
            ]
        )
        == 2
    )
    result = capfd.readouterr()
    assert result.out == "" and result.err == "apizr expose: evidence_invalid\n"


@pytest.mark.parametrize(
    "fault",
    [
        "tamper",
        "schema",
        "extra",
        "duplicate",
        "link",
        "missing",
        "noncanonical",
        "wrong-interface",
    ],
)
def test_refuse_invalid_or_incompatible_documents(inputs, tmp_path, fault):
    bundle, output = tmp_path / "bundle", tmp_path / "evidence"
    write_bundle(bundle, render_repository_bundle(*inputs, interface="rest"))
    manifest = export_evidence(bundle, output, interface="rest")
    path = output / "repository-interface.json"
    expected = identity(manifest)
    if fault == "tamper":
        path.write_bytes(path.read_bytes() + b" ")
    elif fault in {"schema", "extra", "duplicate"}:
        value = json.loads(path.read_bytes())
        if fault == "schema":
            value["schema_version"] = "apizr.repository-interface/v2"
        else:
            value["enterprise_approval"] = True
        raw = json.dumps(value).encode()
        if fault == "duplicate":
            raw = raw[:-1] + b',"enterprise_approval":false}'
        path.write_bytes(raw)
        # Even a recomputed transport hash must not permit unsupported schema.
        artifacts = manifest.artifacts | {
            "repository-interface.json": Digest.of_bytes(raw)
        }
        manifest = manifest.model_copy(update={"artifacts": artifacts})
        raw_manifest = canonical_bytes(manifest)
        (output / "apizr-repository-rest.json").write_bytes(raw_manifest)
        expected = Digest.of_bytes(raw_manifest)
    elif fault == "link":
        path.unlink()
        path.symlink_to(bundle / path.name)
    elif fault == "missing":
        path.unlink()
    elif fault == "noncanonical":
        raw = json.dumps(manifest.model_dump(mode="json"), indent=2).encode()
        (output / "apizr-repository-rest.json").write_bytes(raw)
        expected = Digest.of_bytes(raw)
    with pytest.raises((OSError, ValueError)):
        verify_evidence(
            output,
            interface="mcp" if fault == "wrong-interface" else "rest",
            expected=expected,
        )


def test_bounded_read_and_no_traversal(tmp_path):
    (tmp_path / "value.json").write_text('{"value":1234}')
    with pytest.raises(ValueError, match="size limit"):
        read_document(tmp_path, "value.json", 3)
    with pytest.raises(ValueError, match="filename"):
        read_document(tmp_path, "../value.json")
    (tmp_path / "directory.json").mkdir()
    with pytest.raises((ValueError, OSError)):
        read_document(tmp_path, "directory.json")


def test_failed_export_leaves_no_partial_output(inputs, tmp_path):
    bundle = tmp_path / "bundle"
    write_bundle(bundle, render_repository_bundle(*inputs, interface="rest"))
    (bundle / "source/shop/api.py").write_text('raise RuntimeError("must not run")')
    with pytest.raises(ValueError):
        export_evidence(bundle, tmp_path / "output", interface="rest")
    assert not (tmp_path / "output").exists()

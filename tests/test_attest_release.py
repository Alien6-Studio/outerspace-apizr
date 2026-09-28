"""A permissive CLI verdict must not bypass the release's stricter policy."""

import importlib.util
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "attest_release", Path(__file__).resolve().parents[1] / "scripts/attest_release.py"
)
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def valid_report():
    return {
        "verdict": "pass",
        "signed_by": "expected-key",
        "warnings": [],
        "checks": [{"name": name, "status": "pass"} for name in release.CHECKS],
    }


def test_requires_all_checks_and_exact_signer():
    release.validate_verdict(valid_report(), "expected-key")
    with pytest.raises(ValueError):
        release.validate_verdict(valid_report(), "other-key")


@pytest.mark.parametrize("name", sorted(release.CHECKS))
@pytest.mark.parametrize("status", ["skipped", "fail"])
def test_overall_pass_cannot_hide_missing_proof(name, status):
    report = valid_report()
    for check in report["checks"]:
        if check["name"] == name:
            check["status"] = status
    with pytest.raises(ValueError):
        release.validate_verdict(report, "expected-key")


@pytest.mark.parametrize("change", ["omitted", "duplicate", "warning", "failed"])
def test_incomplete_ambiguous_or_warned_result_fails(change):
    report = valid_report()
    if change == "omitted":
        report["checks"].pop()
    elif change == "duplicate":
        report["checks"][0] = report["checks"][1]
    elif change == "warning":
        report["warnings"] = ["untrusted timestamp"]
    else:
        report["verdict"] = "fail"
    with pytest.raises(ValueError):
        release.validate_verdict(report, "expected-key")


@pytest.mark.parametrize("kind", ["symlink", "directory", "empty"])
def test_delivery_rejects_non_regular_or_missing_files(tmp_path, kind):
    source = tmp_path / "source"
    source.mkdir()
    if kind == "symlink":
        private = tmp_path / "private"
        private.write_text("not an artifact")
        (source / "file").symlink_to(private)
    elif kind == "directory":
        (source / "nested").mkdir()
    with pytest.raises(ValueError):
        release.copy_files(source, tmp_path / "destination")


def test_failed_signer_removes_key_and_never_produces_archive(tmp_path, monkeypatch):
    (tmp_path / ".attest").mkdir()
    # Deliberately invalid test material; the test never invokes a real signer.
    monkeypatch.setenv("APIZR_ATTEST_SIGNING_KEY", "deliberately-invalid-test-key")
    key_id = "a" * 32

    def fail(*args, **kwargs):
        key = tmp_path / ".attest/keys" / f"{key_id}.key"
        assert key.stat().st_mode & 0o777 == 0o600
        assert "APIZR_ATTEST_SIGNING_KEY" not in os.environ
        raise RuntimeError("signer unavailable")

    monkeypatch.setattr(release.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="signer unavailable"):
        release.sign_delivery(
            Path("attest"),
            tmp_path,
            tmp_path / "output",
            {"key_id": key_id, "tsa_url": "unused"},
        )
    assert not list((tmp_path / ".attest/keys").iterdir())
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize(
    "fault", [None, "old_names", "missing", "extra", "version", "evidence"]
)
def test_receipt_binds_all_distribution_names_from_release_source(
    tmp_path, monkeypatch, fault
):
    import json
    import shutil
    import sys

    source = tmp_path / "source"
    shutil.copytree(release.ROOT / ".attest", source / ".attest")
    dist, evidence = tmp_path / "dist", tmp_path / "evidence"
    dist.mkdir()
    evidence.mkdir()
    projects = [
        (source, "outerspace-apizr"),
        *(
            (source / "plugins" / name, f"outerspace-apizr-{name}")
            for name in ("oci", "attest", "mcp")
        ),
    ]
    for folder, name in projects:
        folder.mkdir(parents=True, exist_ok=True)
        version = (
            "0.4.0rc2" if fault == "version" and name.endswith("mcp") else "0.4.0rc1"
        )
        (folder / "pyproject.toml").write_text(
            f'[project]\nname="{name}"\nversion="{version}"\n'
        )
        wheel_name = (
            name.removeprefix("outerspace-")
            if fault == "old_names" and folder != source
            else name
        )
        for suffix in ("-py3-none-any.whl", ".tar.gz"):
            (dist / f"{wheel_name.replace('-', '_')}-0.4.0rc1{suffix}").write_bytes(
                b"reviewed bytes"
            )
    if fault == "missing":
        next(dist.iterdir()).unlink()
    if fault == "extra":
        (dist / "unreviewed.whl").write_bytes(b"extra")
    (evidence / "ci-evidence.tar.gz").write_bytes(b"evidence")
    if fault != "evidence":
        (evidence / "build-provenance.sigstore.json").write_bytes(b"provenance")
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "attest_release",
            "--source-root",
            str(source),
            "--attest",
            "/unused/attest",
            "--dist",
            str(dist),
            "--evidence",
            str(evidence),
            "--workspace",
            str(workspace),
            "--output",
            str(tmp_path / "output"),
            "--commit",
            "a" * 40,
            "--ci-run",
            "123",
        ],
    )
    signed = []
    monkeypatch.setattr(release, "sign_delivery", lambda *args: signed.append(args))
    if fault:
        with pytest.raises(ValueError):
            release.main()
        assert signed == []
    else:
        release.main()
        assert signed[0][-1] == source
        manifest = json.loads((workspace / "delivery/manifest.json").read_text())
        assert len(manifest["distributions"]) == 8
        assert set(manifest["distributions"]) == {p.name for p in dist.iterdir()}
        assert manifest["source_commit"] == "a" * 40

"""The Formula renderer must fail closed before producing unverified tap source."""

import hashlib
import json
import runpy
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
tool = runpy.run_path(str(ROOT / "scripts/homebrew_formula.py"))
SHA = "a" * 40


def candidate(tmp_path):
    root = tmp_path / "candidate"
    source = root / "dist/outerspace_apizr-0.4.2.tar.gz"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"exact source fixture")
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    (root / "candidate.json").write_text(
        json.dumps(
            {
                "schema": "apizr.release-candidate/v1",
                "repository": "Alien6-Studio/outerspace-apizr",
                "commit": SHA,
                "version": "0.4.2",
                "artifacts": [
                    {
                        "file": "dist/" + source.name,
                        "sha256": sha,
                        "bytes": source.stat().st_size,
                    }
                ],
            }
        )
    )
    return root, source, sha


def test_renderer_is_deterministic_and_keeps_build_inputs_out_of_runtime(tmp_path):
    root, source, sha = candidate(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    first = tool["render"](root, SHA, a, mode="qualification")
    second = tool["render"](root, SHA, b, mode="qualification")
    assert first == second and first["source_sha256"] == sha
    assert (a / "Formula/apizr.rb").read_bytes() == (
        b / "Formula/apizr.rb"
    ).read_bytes()
    formula = (a / "Formula/apizr.rb").read_text()
    assert source.as_uri() in formula and formula.count('  resource "') == 5
    assert "virtualenv_create(libexec, python, system_site_packages: true)" in formula
    assert (
        "build_isolation: true" in formula and "deny_network_access! :build" in formula
    )
    assert "pip_install_and_link resources" not in formula
    assert first["build_inputs_manifest_sha256"] == tool["BUILD_MANIFEST"]
    assert str(tmp_path) not in json.dumps(first)


@pytest.mark.parametrize("change", ["bytes", "commit", "version", "duplicate"])
def test_renderer_rejects_changed_candidate_without_output(tmp_path, change):
    root, source, _ = candidate(tmp_path)
    record = root / "candidate.json"
    d = json.loads(record.read_text())
    if change == "bytes":
        source.write_bytes(b"recompressed")
    elif change == "duplicate":
        d["artifacts"] *= 2
    else:
        d[change] = "wrong"
    record.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        tool["render"](root, SHA, tmp_path / "tap", mode="qualification")
    assert not (tmp_path / "tap").exists()


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/archive.tar.gz",
        "https://localhost/archive.tar.gz",
        "https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/1/artifacts/2",
        "https://example.com/apizr.tar.gz",
        "https://github.com/Alien6-Studio/outerspace-apizr/archive/refs/heads/main.tar.gz",
        "https://github.com/Alien6-Studio/outerspace-apizr/releases/download/v0.4.2/outerspace_apizr-0.4.2.tar.gz",
    ],
)
def test_unsigned_or_arbitrary_publication_source_is_rejected(tmp_path, url):
    root, _, sha = candidate(tmp_path)
    with pytest.raises(ValueError):
        tool["render"](
            root,
            SHA,
            tmp_path / "tap",
            mode="publication",
            source_url=url,
            source_sha256=sha,
        )
    assert not (tmp_path / "tap").exists()


def test_qualification_cannot_accept_publication_overrides(tmp_path):
    root, _, sha = candidate(tmp_path)
    with pytest.raises(ValueError, match="local candidate"):
        tool["render"](
            root, SHA, tmp_path / "tap", mode="qualification", source_sha256=sha
        )


@pytest.mark.parametrize("change", [None, "digest", "mutable", "unsigned-member"])
def test_publication_binds_verified_evidence_and_immutable_asset(
    tmp_path, monkeypatch, change
):
    root, source, sha = candidate(tmp_path)
    url = f"https://github.com/Alien6-Studio/outerspace-apizr/releases/download/v0.4.2/{source.name}"
    evidence, bundle = tmp_path / "evidence.tar.gz", tmp_path / "bundle.json"
    bundle.write_text("test signature boundary")
    with tarfile.open(evidence, "w:gz") as archive:
        archive.add(
            root / "candidate.json",
            arcname="coordinated/release-candidate/candidate.json",
        )
        if change != "unsigned-member":
            archive.add(
                source, arcname="coordinated/release-candidate/dist/" + source.name
            )
    calls = []

    def verify(argv, **kwargs):
        calls.append(argv)
        assert kwargs["check"] is True

    monkeypatch.setattr(tool["subprocess"], "run", verify)
    monkeypatch.setattr(
        tool["subprocess"],
        "check_output",
        lambda *a, **k: json.dumps(
            {
                "immutable": change != "mutable",
                "draft": False,
                "assets": [
                    {
                        "browser_download_url": url,
                        "digest": "sha256:" + ("b" * 64 if change == "digest" else sha),
                        "size": source.stat().st_size,
                    }
                ],
            }
        ).encode(),
    )
    kwargs = {
        "mode": "publication",
        "source_url": url,
        "source_sha256": sha,
        "signed_evidence": evidence,
        "provenance_bundle": bundle,
    }
    if change:
        with pytest.raises(ValueError):
            tool["render"](root, SHA, tmp_path / "tap", **kwargs)
        assert not (tmp_path / "tap").exists()
    else:
        result = tool["render"](root, SHA, tmp_path / "tap", **kwargs)
        assert result["mode"] == "publication"
    assert calls[0][-4:] == [
        "--source-digest",
        SHA,
        "--source-ref",
        "refs/heads/release/0.4.2",
    ]

"""Fail closed on unreviewed or substituted release-build inputs."""

import copy
import hashlib
import io
import json
import runpy
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
tool = runpy.run_path(str(ROOT / "scripts/prepare_homebrew_build_inputs.py"))
proof = runpy.run_path(str(ROOT / "scripts/homebrew_build_proof.py"))


def test_reviewed_build_manifest_is_portable_and_stable(tmp_path):
    expected = tool["manifest"](
        ROOT / "uv.lock", ROOT / "policy/homebrew-build-inputs.json"
    )
    lock = tmp_path / "uv.lock"
    policy = tmp_path / "policy.json"
    lock.write_bytes((ROOT / "uv.lock").read_bytes())
    policy.write_bytes((ROOT / "policy/homebrew-build-inputs.json").read_bytes())
    assert tool["encoded"](tool["manifest"](lock, policy)) == tool["encoded"](expected)
    assert str(ROOT).encode() not in tool["encoded"](expected)
    assert expected["build_only"] is True
    changed = json.loads(policy.read_text())
    changed["build"]["distributions"][0]["sha256"] = "0" * 64
    policy.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="reviewed"):
        tool["manifest"](lock, policy)


@pytest.mark.parametrize(
    "change", ["origin", "conditional", "duplicate", "native-only"]
)
def test_build_closure_requires_unambiguous_reviewed_universal_artifacts(change):
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    hatchling = next(p for p in lock["package"] if p["name"] == "hatchling")
    if change == "origin":
        hatchling["wheels"][0]["url"] = "https://example.org/tool.whl"
    elif change == "conditional":
        hatchling["dependencies"][0]["marker"] = "sys_platform == 'darwin'"
    elif change == "duplicate":
        lock["package"].append(copy.deepcopy(hatchling))
    else:
        hatchling["wheels"][0]["url"] = hatchling["wheels"][0]["url"].replace(
            "py3-none-any", "cp314-cp314-macosx_11_0_arm64"
        )
    with pytest.raises(ValueError):
        tool["locked_inputs"](lock)


def fake_wheel(metadata):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("example-1.0.dist-info/METADATA", metadata)
    return output.getvalue()


@pytest.mark.parametrize(
    "requirement",
    ["unreviewed>=1", "known>=2", "known @ https://example.org/known.whl"],
)
def test_wheel_metadata_cannot_expand_the_reviewed_closure(requirement):
    data = fake_wheel(
        "Name: example\nVersion: 1.0\nRequires-Dist: " + requirement + "\n"
    )
    item = {
        "name": "example",
        "version": "1.0",
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    with pytest.raises(ValueError, match="unreviewed"):
        tool["verify_wheel"](data, item, {"known": "1.0"})


def test_wheel_hash_and_embedded_identity_are_both_verified():
    data = fake_wheel("Name: example\nVersion: 1.0\n")
    item = {
        "name": "example",
        "version": "1.0",
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    tool["verify_wheel"](data, item, {})
    with pytest.raises(ValueError, match="SHA-256"):
        tool["verify_wheel"](data + b"changed", item, {})
    with pytest.raises(ValueError, match="identity"):
        tool["verify_wheel"](data, {**item, "version": "2.0"}, {})


def test_candidate_must_match_selected_commit_and_preserved_bytes(tmp_path):
    (tmp_path / "dist").mkdir()
    source = tmp_path / "dist/outerspace_apizr-0.4.2.tar.gz"
    source.write_bytes(b"selected-candidate")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    candidate = {
        "schema": "apizr.release-candidate/v1",
        "repository": "Alien6-Studio/outerspace-apizr",
        "version": "0.4.2",
        "commit": "a" * 40,
        "artifacts": [
            {
                "file": "dist/" + source.name,
                "bytes": source.stat().st_size,
                "sha256": digest,
            }
        ],
    }
    (tmp_path / "candidate.json").write_text(json.dumps(candidate))
    assert proof["candidate_source"](tmp_path, "a" * 40) == (source, digest)
    with pytest.raises(ValueError, match="identity"):
        proof["candidate_source"](tmp_path, "b" * 40)
    source.write_bytes(b"replacement")
    with pytest.raises(ValueError, match="bytes changed"):
        proof["candidate_source"](tmp_path, "a" * 40)

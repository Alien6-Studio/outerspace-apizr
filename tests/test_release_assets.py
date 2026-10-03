"""Public release names retain qualified bytes and cannot bypass provenance."""

import importlib
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest


@pytest.fixture
def assets(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    return importlib.import_module("prepare_release_assets")


def archive(path, files):
    with tarfile.open(path, "w:gz") as tar:
        for name, content in files.items():
            member = tarfile.TarInfo("./" + name)
            member.size = len(content)
            tar.addfile(member, io.BytesIO(content))


def inputs(root, assets, version="0.4.0"):
    candidate = root / "release-candidate"
    (candidate / "dist").mkdir(parents=True)
    for name in assets.PROJECTS:
        for suffix in ("-py3-none-any.whl", ".tar.gz"):
            (
                candidate / "dist" / (name.replace("-", "_") + "-" + version + suffix)
            ).write_bytes(b"retained package")
    manifest = {
        "schema": "apizr.release-candidate/v1",
        "version": version,
        "commit": "a" * 40,
        "artifacts": [
            assets.record(p, candidate) for p in sorted((candidate / "dist").iterdir())
        ],
    }
    assets.write(candidate / "candidate.json", manifest)
    targets = []
    for system, machine, versions in [
        ("Linux", "x86_64", (11, 12, 13, 14)),
        ("Darwin", "arm64", (11, 14)),
    ]:
        for minor in versions:
            directory = root / f"release-target-{system}-{minor}"
            (directory / "qualification").mkdir(parents=True)
            target = {
                "schema": "apizr.release-target/v1",
                "commit": manifest["commit"],
                "candidate_sha256": assets.digest(candidate / "candidate.json"),
                "target": {
                    "system": system,
                    "machine": machine,
                    "python": f"3.{minor}.1",
                },
                "artifacts": [],
            }
            archive(
                directory / "target-export.tar.gz",
                {"target.json": json.dumps(target).encode()},
            )
            report = {
                **target,
                "core_unchanged": True,
                **dict.fromkeys(
                    (
                        "pip",
                        "uv_tool",
                        "pipx",
                        "catalog_resolve_lock_sync",
                        "migration",
                        "extras_local_https_ssh",
                    ),
                    "passed",
                ),
            }
            assets.write(directory / "qualification/qualification.json", report)
            targets.append(directory)
    (root / "release-delivery").mkdir()
    assets.write(root / "release-delivery/outcome.json", {"exit_code": 0})
    evidence = root / "build-attestations"
    evidence.mkdir()
    archive(
        evidence / "ci-evidence.tar.gz",
        {
            "coordinated/" + p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file() and evidence not in p.parents
        },
    )
    for name in ("build-provenance.sigstore.json", "runtime-sbom.sigstore.json"):
        (evidence / name).write_text(
            "fixture: external signature verification is mocked"
        )
    return targets


@pytest.mark.parametrize(
    "version", ["0.4.0", "0.4.0rc1", "0.4.1rc1", "0.4.1", "0.4.2rc1", "0.4.2", "0.4.3"]
)
def test_stage_preserves_bytes_and_uses_recorded_unique_names(
    assets, tmp_path, monkeypatch, version
):
    downloads = tmp_path / "downloads"
    targets = inputs(downloads, assets, version)
    calls = []
    monkeypatch.setattr(
        assets.subprocess, "run", lambda command, **kw: calls.append(command)
    )
    output = tmp_path / "assets"
    assets.prepare(downloads, output, "a" * 40, 123)
    assert len(calls) == 1
    assert calls[0][:3] == ["gh", "attestation", "verify"]
    assert calls[0][-4:] == [
        "--source-digest",
        "a" * 40,
        "--source-ref",
        "refs/heads/" + assets.qualification_branch(version),
    ]
    manifest = json.loads((output / "release-assets.json").read_text())
    assert "human publication approval still required" in manifest["status"]
    assert len(manifest["artifacts"]) == 24
    for target in targets:
        _, suffix = assets.inspect_target(
            target / "target-export.tar.gz", {"commit": "a" * 40}
        )
        assert (output / f"apizr-{version}-{suffix}.tar.gz").read_bytes() == (
            target / "target-export.tar.gz"
        ).read_bytes()
    for line in (output / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ")
        assert digest == assets.digest(output / name)
    assert not manifest["official_images"]["published"]


@pytest.mark.parametrize(
    ("event", "ref", "preview"),
    [
        ("pull_request", "refs/pull/205/merge", True),
        ("push", "refs/heads/master", True),
        ("push", "refs/heads/release/0.4.2", True),
        ("push", "refs/heads/release/0.4.3", True),
        ("push", "refs/heads/release/0.4.1", True),
    ],
)
def test_current_workflow_cannot_requalify_retired_release_refs(
    assets, tmp_path, monkeypatch, event, ref, preview
):
    import yaml

    workflow = yaml.load(
        (Path(__file__).parents[1] / ".github/workflows/ci.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    step = next(
        step
        for step in workflow["jobs"]["release-assets"]["steps"]
        if step.get("name") == "Prepare attachments; never upload to a release"
    )
    # Execute the actual workflow's argument selection without invoking CI tools.
    selected = subprocess.check_output(
        ["bash", "-c", "python3() { printf '%s\\n' \"$@\"; }\n" + step["run"]],
        env={
            **os.environ,
            "EVENT_NAME": event,
            "GITHUB_REF": ref,
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
        },
        text=True,
    ).splitlines()
    assert ("--preview" in selected) is preview
    downloads = tmp_path / "downloads"
    inputs(
        downloads, assets, "0.4.3" if ref == "refs/heads/release/0.4.3" else "0.4.2rc1"
    )
    calls = []
    monkeypatch.setattr(
        assets.subprocess, "run", lambda command, **kw: calls.append(command)
    )
    output = tmp_path / "assets"
    assets.prepare(downloads, output, "a" * 40, 123, preview=preview, source_ref=ref)
    manifest = json.loads((output / "release-assets.json").read_text())
    assert manifest["source_ref"] == (None if preview else ref)
    assert bool(calls) is not preview
    assert (output / "ci-evidence.tar.gz").exists() is not preview
    if preview:
        assert manifest["status"] == "verification preview; no release provenance"


@pytest.mark.parametrize(
    "fault",
    [
        "signature",
        "candidate",
        "unsigned_target",
        "unsigned_report",
        "qualification",
        "collision",
        "delivery",
    ],
)
def test_failed_verification_never_exposes_attachments(
    assets, tmp_path, monkeypatch, fault
):
    downloads = tmp_path / "downloads"
    targets = inputs(downloads, assets)

    def verify(*args, **kwargs):
        if fault == "signature":
            raise subprocess.CalledProcessError(1, ["gh", "attestation", "verify"])

    monkeypatch.setattr(assets.subprocess, "run", verify)
    if fault == "candidate":
        next((downloads / "release-candidate/dist").iterdir()).write_bytes(b"changed")
    elif fault in ("unsigned_target", "collision"):
        source = targets[0] / "target-export.tar.gz"
        if fault == "collision":
            (targets[1] / source.name).write_bytes(source.read_bytes())
            (targets[1] / "qualification/qualification.json").write_bytes(
                (targets[0] / "qualification/qualification.json").read_bytes()
            )
        else:
            with tarfile.open(source) as tar:
                value = json.loads(assets.member_bytes(tar, "target.json"))
            value["extra"] = "not signed"
            archive(source, {"target.json": json.dumps(value).encode()})
    elif fault in ("unsigned_report", "qualification"):
        path = targets[0] / "qualification/qualification.json"
        value = json.loads(path.read_text())
        value["pip"] = "failure" if fault == "qualification" else "passed"
        value["extra"] = "not signed"
        assets.write(path, value)
    elif fault == "delivery":
        assets.write(downloads / "release-delivery/outcome.json", {"exit_code": 1})
    output = tmp_path / "assets"
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        assets.prepare(downloads, output, "a" * 40, 123, preview=fault == "collision")
    assert not output.exists()
    assert not list(tmp_path.glob(".release-assets-*"))


@pytest.mark.parametrize("name", ["../escape", "extra.whl"])
def test_target_export_rejects_unrecorded_and_escaping_files(assets, tmp_path, name):
    target = {"schema": "apizr.release-target/v1", "commit": "a" * 40, "artifacts": []}
    path = tmp_path / "target.tar.gz"
    archive(path, {"target.json": json.dumps(target).encode(), name: b"unapproved"})
    with pytest.raises(ValueError):
        assets.inspect_target(path, {"commit": "a" * 40})


@pytest.mark.parametrize(
    "source_ref",
    ["refs/heads/master", "refs/heads/feature", "refs/heads/release/0.4.2"],
)
def test_041_assets_refuse_wrong_provenance_ref(
    assets, tmp_path, monkeypatch, source_ref
):
    downloads = tmp_path / "downloads"
    inputs(downloads, assets, "0.4.1rc1")
    monkeypatch.setattr(
        assets.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("no verification with wrong ref"),
    )
    output = tmp_path / "assets"
    with pytest.raises(ValueError, match="Unexpected qualification source ref"):
        assets.prepare(downloads, output, "a" * 40, 123, source_ref=source_ref)
    assert not output.exists()


def test_inherited_version_on_release_line_is_only_verification_evidence(
    assets, tmp_path, monkeypatch
):
    downloads = tmp_path / "downloads"
    inputs(downloads, assets, "0.4.0rc1")
    calls = []
    monkeypatch.setattr(
        assets.subprocess, "run", lambda command, **kw: calls.append(command)
    )
    output = tmp_path / "assets"
    assets.prepare(
        downloads, output, "a" * 40, 123, source_ref="refs/heads/release/0.4.1"
    )
    assert calls[0][-1] == "refs/heads/release/0.4.1"
    manifest = json.loads((output / "release-assets.json").read_text())
    assert manifest["source_ref"] == "refs/heads/release/0.4.1"
    assert "human publication approval still required" in manifest["status"]

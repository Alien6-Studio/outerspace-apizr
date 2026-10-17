"""Stale public text must fail before building and after a candidate is frozen."""

import io
import json
import shutil
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.qualification.packaging import check_release_metadata as gate
from scripts.qualification.packaging import coordinated_distributions as packaging


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    for name in gate.inventory("0.4.6"):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(gate.ROOT / name, target)
    return root


@pytest.fixture
def release(source):
    root = source
    for path in root.rglob("*"):
        if path.is_file():
            path.write_text(path.read_text().replace("0.4.5", "0.4.6"))
    (root / gate.POLICY).write_text(
        'schema_version = 1\n[release]\nversion = "0.4.6"\n'
    )
    for directory in gate.PROJECTS:
        (root / directory / "README.md").write_text(
            "# Apizr\n\nApizr **0.4.6** compiles Python capabilities.\n\n"
            "```sh\nuv tool install outerspace-apizr==0.4.6\n```\n\n"
            f"[Source]({gate.REPOSITORY}/tree/v0.4.6/)\n"
        )
    (root / "docs/getting-started/install.md").write_text(
        "# Install Apizr\n\nInstall Apizr 0.4.6.\n\n"
        "```sh\npython -m pip install outerspace-apizr==0.4.6\n```\n"
        "Observe `outerspace-apizr 0.4.6`.\n"
    )
    docker = root / "Dockerfile"
    docker.write_text(
        docker.read_text().replace("ARG SOURCE_REF=0.4.6", "ARG SOURCE_REF=v0.4.6")
    )
    return root


@pytest.fixture
def development(release):
    root = release
    for path in root.rglob("*"):
        if path.is_file():
            path.write_text(path.read_text().replace("0.4.6", "0.4.5"))
    (root / gate.POLICY).write_text(
        'schema_version=1\n[release]\nversion="0.4.6"\n[development]\nbranch="0.4.6"\npackage_version="0.4.5"\npublished_version="0.4.5"\nreason="Explicit test-only inherited metadata"\n'
    )
    for name in (
        "README.md",
        "plugins/oci/README.md",
        "plugins/attest/README.md",
        "plugins/mcp/README.md",
        "docs/getting-started/install.md",
    ):
        path = root / name
        path.write_text("<!-- apizr-development: 0.4.6 -->\n" + path.read_text())
    for name in ("CHANGELOG.md", "docs/releases/0.4.6.md"):
        path = root / name
        path.write_text(path.read_text().replace("# 0.4.5", "# 0.4.6"))
    (root / "Dockerfile").write_text(
        (root / "Dockerfile")
        .read_text()
        .replace("ARG SOURCE_REF=v0.4.5", "ARG SOURCE_REF=0.4.6")
    )
    return root


def test_inherited_version_is_explicit_and_never_publishable(development):
    result = gate.check(development, ref="refs/heads/0.4.6")
    assert result["mode"] == "development" and not result["release_metadata_ready"]
    assert result["version"] == "0.4.5" and result["target_version"] == "0.4.6"
    for ref in (
        "refs/tags/v0.4.5",
        "refs/tags/v0.4.6",
        "refs/heads/master",
        "refs/heads/release/0.4.6",
    ):
        with pytest.raises(ValueError, match="Development metadata marker"):
            gate.check(development, ref=ref)
    with pytest.raises(ValueError, match="Development metadata marker"):
        gate.check(development, release=True, ref="refs/heads/0.4.6")


def test_missing_development_marker_is_not_an_implicit_exception(development):
    path = development / "README.md"
    path.write_text(path.read_text().replace("<!-- apizr-development: 0.4.6 -->", ""))
    with pytest.raises(ValueError, match="missing explicit development marker"):
        gate.check(development, ref="refs/heads/0.4.6")


def test_complete_release_metadata_passes_without_publication_authorization(release):
    result = gate.check(release, release=True, ref="refs/tags/v0.4.6")
    assert result["mode"] == "release" and result["release_metadata_ready"]
    assert result["publication_performed"] is False
    assert len(result["files"]) == len(gate.inventory("0.4.6"))


@pytest.mark.parametrize(
    "path,text",
    [
        ("README.md", "\nApizr 0.4.2 has this feature.\n"),
        ("README.md", "\nThe published 0.4.2 feature.\n"),
        ("README.md", "\n## Inspect (0.4.2)\n"),
        ("README.md", "\nuv tool install outerspace-apizr==0.4.5\n"),
        ("README.md", "\nouterspace_apizr-0.4.5-py3-none-any.whl\n"),
        (
            "README.md",
            "\n[Source](https://github.com/Alien6-Studio/outerspace-apizr/tree/0.4.6/)\n",
        ),
        (
            "README.md",
            "\n[Source](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/README.md)\n",
        ),
        ("plugins/mcp/README.md", "\nNot yet published.\n"),
        ("README.md", "\nuv tool install outerspace-apizr[notebook]==0.4.5\n"),
        ("plugins/mcp/README.md", "\nuvx outerspace-apizr-mcp@0.4.5\n"),
        ("plugins/oci/README.md", "\nApizr 0.4.3 is the stable baseline.\n"),
        ("plugins/attest/README.md", "\nThis release candidate adds receipts.\n"),
        ("docs/getting-started/install.md", "\nObserve outerspace-apizr 0.4.5.\n"),
        ("docs/getting-started/install.md", "\n${APIZR_VERSION:-0.4.5}\n"),
    ],
)
def test_old_prose_pins_and_mutable_links_block_release(release, path, text):
    selected = release / path
    selected.write_text(selected.read_text() + text)
    with pytest.raises(ValueError, match="Release metadata refused"):
        gate.check(release, release=True)


@pytest.mark.parametrize(
    "name,old,new",
    [
        ("plugins/mcp/pyproject.toml", 'version = "0.4.6"', 'version = "0.4.5"'),
        (
            "plugins/oci/pyproject.toml",
            "outerspace-apizr==0.4.6",
            "outerspace-apizr==0.4.5",
        ),
        (
            "plugins/attest/pyproject.toml",
            "outerspace-apizr-oci==0.4.6",
            "outerspace-apizr-oci==0.4.5",
        ),
        ("plugins/mcp/pyproject.toml", "Issues = ", "WrongIssues = "),
        ("plugins/oci/pyproject.toml", "v0.4.6/CHANGELOG", "v0.4.5/CHANGELOG"),
        ("plugins/attest/apizr-extension.json", '"0.4.6"', '"0.4.5"'),
        ("server.json", '"version": "0.4.6"', '"version": "0.4.5"'),
        ("action.yml", "default: 0.4.6", "default: 0.4.5"),
        ("templates/apizr.yml", "default: 0.4.6", "default: 0.4.5"),
        ("Dockerfile", "ARG SOURCE_REF=v0.4.6", "ARG SOURCE_REF=master"),
        ("CHANGELOG.md", "## 0.4.6", "## 0.4.5"),
        ("docs/releases/0.4.6.md", "# 0.4.6", "# 0.4.5"),
    ],
)
def test_each_public_surface_rejects_version_drift(release, name, old, new):
    path = release / name
    assert old in path.read_text()
    path.write_text(path.read_text().replace(old, new))
    with pytest.raises(ValueError):
        gate.check(release, release=True)


def test_same_version_readme_edit_invalidates_the_frozen_candidate(release):
    snapshot = gate.check(release, release=True)
    path = release / "plugins/mcp/README.md"
    path.write_text(path.read_text() + "\nA same-version editorial change.\n")
    gate.check(release, release=True)
    with pytest.raises(ValueError, match="changed after candidate build"):
        gate.verify_snapshot(release, snapshot, release=True)


def archives(root, dist):
    dist.mkdir()
    for directory in gate.PROJECTS:
        project = gate.tomllib.loads((root / directory / "pyproject.toml").read_text())[
            "project"
        ]
        stem, version = project["name"].replace("-", "_"), project["version"]
        readme = (root / directory / "README.md").read_bytes()
        metadata = (
            f"Metadata-Version: 2.4\nName: {project['name']}\nVersion: {version}\n"
            + "".join(
                f"Project-URL: {key}, {value}\n"
                for key, value in project["urls"].items()
            )
            + "\n"
        ).encode() + readme
        with zipfile.ZipFile(
            dist / f"{stem}-{version}-py3-none-any.whl", "w"
        ) as archive:
            archive.writestr(f"{stem}-{version}.dist-info/METADATA", metadata)
        with tarfile.open(dist / f"{stem}-{version}.tar.gz", "w:gz") as archive:
            member = tarfile.TarInfo(f"{stem}-{version}/PKG-INFO")
            member.size = len(metadata)
            archive.addfile(member, io.BytesIO(metadata))


@pytest.mark.parametrize("fault", [None, "description", "urls"])
def test_downloaded_archive_readme_and_urls_equal_tagged_source(
    release, tmp_path, fault
):
    dist = tmp_path / "dist"
    archives(release, dist)
    gate.verify_archives(release, dist)
    path = dist / "outerspace_apizr_mcp-0.4.6-py3-none-any.whl"
    if fault:
        with zipfile.ZipFile(path) as archive:
            name = archive.namelist()[0]
            raw = archive.read(name)
        raw = (
            raw + b"Changed frozen prose.\n"
            if fault == "description"
            else raw.replace(b"Project-URL: Issues,", b"Project-URL: WrongIssues,")
        )
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(name, raw)
        with pytest.raises(ValueError, match="Frozen"):
            gate.verify_archives(release, dist)


def test_stale_text_refuses_before_any_build_or_output(release, tmp_path, monkeypatch):
    (release / "README.md").write_text("Apizr 0.4.5\n")
    monkeypatch.setattr(packaging, "ROOT", release)
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        assert args == ("git", "status", "--porcelain"), (
            "Cannot reach a build before metadata admission"
        )
        return ""

    monkeypatch.setattr(packaging, "run", run)
    output = tmp_path / "candidate"
    with pytest.raises(ValueError, match="stale Apizr statements"):
        packaging.build(output)
    assert len(calls) == 1 and not output.exists()


@pytest.fixture
def qualified(release, tmp_path, monkeypatch):
    from release_candidate_helpers import attach_editor

    candidate, dist = tmp_path / "candidate", tmp_path / "dist"
    candidate.mkdir()
    archives(release, dist)
    snapshot = candidate / "release-metadata.json"
    snapshot.write_text(json.dumps(gate.check(release, release=True)))
    manifest = {
        "schema": "apizr.release-candidate/v1",
        "repository": "Alien6-Studio/outerspace-apizr",
        "commit": "a" * 40,
        "version": "0.4.6",
        "release_metadata": {
            "file": snapshot.name,
            "bytes": snapshot.stat().st_size,
            "sha256": gate.sha(snapshot.read_bytes()),
        },
        "artifacts": [
            {
                "file": "dist/" + p.name,
                "bytes": p.stat().st_size,
                "sha256": gate.sha(p.read_bytes()),
            }
            for p in sorted(dist.iterdir())
        ],
    }
    attach_editor(candidate, manifest, release)
    (candidate / "candidate.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(gate.subprocess, "check_output", lambda *a, **kw: "a" * 40)
    return release, candidate, dist


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "commit",
        "version",
        "repository",
        "schema",
        "snapshot",
        "snapshot-path",
        "duplicate",
        "extra",
        "archive",
        "editorial",
    ],
)
def test_publication_requires_original_candidate_and_exact_tagged_text(
    qualified, fault
):
    root, candidate, dist = qualified
    path = candidate / "candidate.json"
    manifest = json.loads(path.read_text())
    if fault in {"commit", "version", "repository", "schema"}:
        manifest[fault] = "wrong"
    elif fault == "snapshot":
        (candidate / "release-metadata.json").write_text("{}")
    elif fault == "snapshot-path":
        manifest["release_metadata"]["file"] = "../release-metadata.json"
    elif fault == "duplicate":
        manifest["artifacts"][-1] = manifest["artifacts"][0]
    elif fault == "extra":
        (dist / "extra.whl").write_bytes(b"extra")
    elif fault == "archive":
        (dist / Path(manifest["artifacts"][0]["file"]).name).write_bytes(b"tampered")
    elif fault == "editorial":
        readme = root / "README.md"
        readme.write_text(readme.read_text() + "\nSame-version editorial update.\n")
    path.write_text(json.dumps(manifest))
    if fault:
        with pytest.raises(ValueError):
            gate.verify_candidate(root, candidate, dist)
    else:
        report = gate.verify_candidate(root, candidate, dist)
        assert report["qualified_archives"] == 8
        assert report["candidate_commit"] == "a" * 40
        assert report["publication_performed"] is False


@pytest.mark.parametrize("fault", [None, "missing", "digest", "downloaded-bytes"])
def test_postpublication_compares_actual_downloaded_bytes(
    qualified, monkeypatch, fault
):
    from scripts.qualification.packaging import prepare_publication as public

    root, candidate, dist = qualified
    downloads = []

    def metadata(name, version):
        records = {}
        for p in dist.glob(name.replace("-", "_") + "-" + version + "*"):
            records[p.name] = {
                "digests": {"sha256": gate.sha(p.read_bytes())},
                "size": p.stat().st_size,
                "url": "https://files.pythonhosted.org/" + p.name,
            }
        if fault == "missing":
            records.pop(next(iter(records)))
        elif fault == "digest":
            records[next(iter(records))]["digests"]["sha256"] = "b" * 64
        return records

    def download(url, **kwargs):
        downloads.append(url)
        content = (dist / url.rsplit("/", 1)[-1]).read_bytes()
        return io.BytesIO(content if fault != "downloaded-bytes" else b"different")

    monkeypatch.setattr(public, "public_files", metadata)
    monkeypatch.setattr(public.urllib.request, "urlopen", download)
    if fault:
        with pytest.raises(ValueError, match="Public"):
            gate.verify_public(root, candidate, dist)
    else:
        report = gate.verify_public(root, candidate, dist)
        assert report["public_archive_bytes_equal"] is True and len(downloads) == 8
        assert report["publication_performed"] is False


def test_publication_workflows_cannot_skip_metadata_before_side_effects():
    import yaml

    workflow = yaml.safe_load(
        (gate.ROOT / ".github/workflows/publish-pypi.yml").read_text()
    )
    jobs = workflow["jobs"]
    preflight = next(
        s
        for s in jobs["verify"]["steps"]
        if "--candidate metadata-candidate" in s.get("run", "")
    )
    assert "--source-root release-source" in preflight["run"]
    assert "--release" in preflight["run"]
    assert "verify" in jobs["publish"]["needs"]
    assert any("--public" in s.get("run", "") for s in jobs["verify-public"]["steps"])
    for name in ("publish-mcp.yml", "verify-mcp-distribution.yml"):
        text = (gate.ROOT / ".github/workflows" / name).read_text()
        assert "verify_mcp_publication.py" in text


@pytest.mark.parametrize("fault", [None, "wrong-commit", "link", "changed-blob"])
def test_revision_comparison_reads_only_regular_tagged_blobs(
    qualified, monkeypatch, tmp_path, fault
):
    import subprocess

    root, candidate, dist = qualified
    monkeypatch.undo()

    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "user.name=Qualification",
                "-c",
                "user.email=qualification@example.invalid",
                *args,
            ],
            cwd=root,
            text=True,
        ).strip()

    marker = tmp_path / "source-was-executed"
    (root / "scripts").mkdir()
    (root / "scripts/prepare_publication.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    )
    if fault == "link":
        path = root / "README.md"
        raw = path.read_text()
        path.unlink()
        (root / "unrelated-readme").write_text(raw)
        path.symlink_to("unrelated-readme")
    git("init", "--quiet", "--initial-branch=fixture")
    git("add", ".")
    git("commit", "--quiet", "-m", "metadata fixture")
    revision = git("rev-parse", "HEAD")
    manifest = json.loads((candidate / "candidate.json").read_text())
    manifest["commit"] = revision if fault != "wrong-commit" else "a" * 40
    proof = candidate / "editor/apizr-0.4.6.json"
    data = json.loads(proof.read_text())
    data["source_commit"] = manifest["commit"]
    proof.write_text(json.dumps(data))
    manifest["editor_evidence"] = [
        packaging.record(candidate / i["file"], candidate)
        for i in manifest["editor_evidence"]
    ]
    (candidate / "candidate.json").write_text(json.dumps(manifest))
    if fault == "changed-blob":
        (root / "README.md").write_text("Different committed metadata\n")
        git("add", ".")
        git("commit", "--quiet", "-m", "changed metadata")
        revision = git("rev-parse", "HEAD")
        manifest["commit"] = revision
        (candidate / "candidate.json").write_text(json.dumps(manifest))
    elif fault != "link":
        # Working-tree edits must not replace the selected immutable Git blobs.
        (root / "README.md").write_text("Uncommitted working-tree text\n")
    if fault:
        with pytest.raises(ValueError):
            gate.verify_revision(root, revision, candidate, dist)
    else:
        result = gate.verify_revision(root, revision, candidate, dist)
        assert result["candidate_commit"] == revision
        assert result["qualified_archives"] == 8
    assert not marker.exists()


@pytest.mark.parametrize(
    "revision", ["HEAD", "v0.4.6", "a" * 39, "--help", "../README.md"]
)
def test_revision_comparison_refuses_mutable_refs_before_git(
    tmp_path, revision, monkeypatch
):
    monkeypatch.setattr(
        gate.subprocess,
        "check_output",
        lambda *a, **kw: pytest.fail("no Git call for invalid revision"),
    )
    with pytest.raises(ValueError, match="full source commit"):
        gate.verify_revision(tmp_path, revision, tmp_path, tmp_path)

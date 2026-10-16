"""Stale public text must fail before building and after a candidate is frozen."""

import io
import shutil
import tarfile
import zipfile

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

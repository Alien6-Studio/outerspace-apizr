"""Release artifacts cannot silently change identity or reuse another commit."""

import importlib
import json
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def packaging(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    module = importlib.import_module(
        "scripts.qualification.packaging.coordinated_distributions"
    )
    monkeypatch.setattr(module, "source_commit", lambda: "a" * 40)
    return module


def candidate(root, packaging):
    (root / "dist").mkdir()
    for name in packaging.PROJECTS:
        for suffix in ("-py3-none-any.whl", ".tar.gz"):
            (root / "dist" / (name.replace("-", "_") + "-0.4.0" + suffix)).write_bytes(
                b"retained archive"
            )
    value = {
        "schema": "apizr.release-candidate/v1",
        "version": "0.4.0",
        "commit": "a" * 40,
        "artifacts": [
            packaging.record(path, root) for path in sorted((root / "dist").iterdir())
        ],
    }
    packaging.write(root / "candidate.json", value)
    return value


@pytest.mark.parametrize(
    "fault",
    ["commit", "missing", "bytes", "size", "path", "duplicate", "link", "extra"],
)
def test_retained_set_rejects_mismatch(packaging, tmp_path, fault):
    value = candidate(tmp_path, packaging)
    assert packaging.load(tmp_path) == value
    item = value["artifacts"][0]
    path = tmp_path / item["file"]
    if fault == "commit":
        value["commit"] = "b" * 40
    elif fault == "missing":
        path.unlink()
    elif fault == "bytes":
        path.write_bytes(b"different bytes!")
    elif fault == "size":
        item["bytes"] += 1
    elif fault == "path":
        item["file"] = "../" + path.name
    elif fault == "duplicate":
        value["artifacts"].append(item)
    elif fault == "extra":
        (tmp_path / "dist/.gitignore").write_text("*")
    elif fault == "link":
        other = tmp_path / "outside"
        path.rename(other)
        path.symlink_to(other)
    packaging.write(tmp_path / "candidate.json", value)
    with pytest.raises(ValueError):
        packaging.load(tmp_path)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "downgrade",
        "missing",
        "kind",
        "bytes",
        "commit",
        "dirty",
        "fixture",
        "reproducibility",
        "licences",
        "proof-files",
        "client-source",
    ],
)
def test_coordinated_vsix_is_source_bound_and_cannot_be_omitted(
    packaging, tmp_path, fault
):
    from release_candidate_helpers import attach_editor

    value = candidate(tmp_path, packaging)
    value["version"] = "0.4.6"
    for item in value["artifacts"]:
        path = tmp_path / item["file"]
        renamed = path.with_name(path.name.replace("0.4.0", "0.4.6"))
        path.rename(renamed)
    value["artifacts"] = [
        packaging.record(p, tmp_path) for p in sorted((tmp_path / "dist").iterdir())
    ]
    attach_editor(tmp_path, value, packaging.ROOT)
    snapshot = tmp_path / "release-metadata.json"
    packaging.write(snapshot, packaging.check_release_metadata(packaging.ROOT))
    value["release_metadata"] = packaging.record(snapshot, tmp_path)
    proof_path = tmp_path / "editor/apizr-0.4.6.json"
    proof = json.loads(proof_path.read_text())
    if fault == "downgrade":
        value["schema"] = "apizr.release-candidate/v1"
        value["artifacts"] = value["artifacts"][:-1]
    elif fault == "missing":
        value["artifacts"].pop()
    elif fault == "kind":
        value["artifacts"][-1]["kind"] = "wheel"
    elif fault == "bytes":
        (tmp_path / value["artifacts"][-1]["file"]).write_bytes(b"replacement")
    elif fault == "commit":
        proof["source_commit"] = "b" * 40
    elif fault == "client-source":
        proof["client_source"]["commit"] = "b" * 40
    elif fault == "dirty":
        proof["source_dirty"] = True
    elif fault == "fixture":
        proof["qualification_fixture"] = True
    elif fault == "reproducibility":
        proof["repeated_build_identical"] = False
    elif fault == "proof-files":
        proof["files"].pop(next(iter(proof["files"])))
    elif fault == "licences":
        packaging.write(
            tmp_path / "editor/dependency-licenses.json",
            {"result": "pass", "runtime_dependencies": 0, "packages": {}},
        )
    packaging.write(proof_path, proof)
    value["editor_evidence"] = [
        packaging.record(tmp_path / i["file"], tmp_path)
        for i in value["editor_evidence"]
    ]
    packaging.write(tmp_path / "candidate.json", value)
    if fault:
        with pytest.raises(ValueError):
            packaging.load(tmp_path)
    else:
        assert packaging.load(tmp_path) == value
        assert len(value["artifacts"]) == 9


@pytest.mark.parametrize("image", ["experiments.png", "run-review.gif"])
def test_vsix_rejects_changed_documentation_image(packaging, tmp_path, image):
    from release_candidate_helpers import attach_editor

    attach_editor(
        tmp_path,
        {"version": "0.4.6", "commit": "a" * 40, "artifacts": []},
        packaging.ROOT,
    )
    path = tmp_path / "editor/apizr-0.4.6.vsix"
    with zipfile.ZipFile(path) as archive:
        payload = [(info, archive.read(info.filename)) for info in archive.infolist()]
    with zipfile.ZipFile(path, "w") as archive:
        for info, raw in payload:
            if info.filename == "extension/media/screenshots/" + image:
                raw += b"changed after review"
            archive.writestr(info, raw)
    with pytest.raises(
        ValueError, match="VSIX source/notice differs: media/screenshots/"
    ):
        packaging.check_vsix(path, packaging.ROOT)


@pytest.mark.parametrize("fault", [None, "source", "native"])
def test_only_locked_pure_yaml_can_be_prepared_from_source(
    packaging, tmp_path, monkeypatch, fault
):
    import hashlib
    import zipfile

    house = tmp_path / "extras"
    house.mkdir()
    source = house / "pyyaml-6.0.3.tar.gz"
    content = b"locked upstream source"
    lock = tmp_path / "resolved.txt"
    lock.write_text("pyyaml==6.0.3\n")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname="pyyaml"\nversion="6.0.3"\n'
        'sdist={hash="sha256:' + hashlib.sha256(content).hexdigest() + '"}\n'
    )
    monkeypatch.setattr(packaging, "ROOT", tmp_path)
    monkeypatch.setattr(packaging.sys, "version_info", (3, 15))
    calls = []

    def prepare(*args, **kwargs):
        calls.append(args)
        if "download" in args:
            assert "--require-hashes" in args and "--only-binary=:all:" in args
            assert "--no-binary=pyyaml" in args
            source.write_bytes(b"tampered" if fault == "source" else content)
        else:
            env = kwargs["env"]
            assert env["PYYAML_FORCE_LIBYAML"] == "0"
            assert env["CC"] == env["CXX"] == env["RUSTC"] == "/usr/bin/false"
            with zipfile.ZipFile(house / "pyyaml-6.0.3-py3-none-any.whl", "w") as wheel:
                wheel.writestr(
                    "pyyaml-6.0.3.dist-info/METADATA", "Name: PyYAML\nVersion: 6.0.3\n"
                )
                if fault == "native":
                    wheel.writestr("yaml/_yaml.so", b"native extension")
        return "prepared without native compilation\n"

    monkeypatch.setattr(packaging, "run", prepare)
    if fault:
        with pytest.raises(ValueError, match="(locked|pure-Python)"):
            packaging.download_closure(tmp_path / "python", lock, house)
        assert not (tmp_path / "pyyaml-build/provenance.json").exists()
        if fault == "source":
            assert len(calls) == 1
    else:
        packaging.download_closure(tmp_path / "python", lock, house)
        assert not source.exists()
        evidence = json.loads((tmp_path / "pyyaml-build/provenance.json").read_text())
        assert (
            evidence["upstream_source"]["sha256"] == hashlib.sha256(content).hexdigest()
        )
        assert evidence["prepared_wheel"]["file"].endswith("py3-none-any.whl")


def test_candidate_proof_never_falls_back_to_rebuild(packaging, tmp_path, monkeypatch):
    monkeypatch.setenv("APIZR_RELEASE_SET", str(tmp_path))
    monkeypatch.delenv("APIZR_RELEASE_TARGET", raising=False)
    with pytest.raises(ValueError, match="explicit matching"):
        packaging.copy_closure("mcp", tmp_path / "destination")
    assert not (tmp_path / "destination").exists()


@pytest.fixture
def publication(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    return importlib.import_module(
        "scripts.qualification.packaging.prepare_publication"
    )


@pytest.mark.parametrize("fault", ["different", "extra", "network"])
def test_partial_publication_fails_closed(publication, tmp_path, monkeypatch, fault):
    dist = tmp_path / "dist"
    dist.mkdir()
    for name in publication.PACKAGES:
        for suffix in ("-py3-none-any.whl", ".tar.gz"):
            (dist / (name.replace("-", "_") + "-0.4.0" + suffix)).write_bytes(
                b"approved"
            )

    def public(name, version):
        if fault == "network":
            raise OSError("unavailable")
        filename = (
            "unexpected.whl"
            if fault == "extra"
            else "outerspace_apizr-0.4.0-py3-none-any.whl"
        )
        return {filename: {}} if name == "outerspace-apizr" else {}

    monkeypatch.setattr(publication, "public_files", public)
    monkeypatch.setattr(publication, "matches", lambda *args: False)
    with pytest.raises((ValueError, OSError)):
        publication.stage(dist, tmp_path / "pending", "0.4.0")
    assert not (tmp_path / "pending").exists()


def test_partial_identical_upload_stages_only_missing_bytes(
    publication, tmp_path, monkeypatch
):
    dist = tmp_path / "dist"
    dist.mkdir()
    for name in publication.PACKAGES:
        for suffix in ("-py3-none-any.whl", ".tar.gz"):
            (dist / (name.replace("-", "_") + "-0.4.0" + suffix)).write_bytes(
                b"approved"
            )
    filename = "outerspace_apizr-0.4.0-py3-none-any.whl"
    monkeypatch.setattr(
        publication,
        "public_files",
        lambda name, version: {filename: {}} if name == "outerspace-apizr" else {},
    )
    monkeypatch.setattr(publication, "matches", lambda *args: True)
    output = tmp_path / "pending"
    result = publication.stage(dist, output, "0.4.0")
    assert result["outerspace-apizr"][filename] == "public-byte-identical"
    assert not (output / "outerspace-apizr" / filename).exists()
    assert len(list(output.rglob("*.whl"))) == 3
    assert len(list(output.rglob("*.tar.gz"))) == 4
    assert json.loads((output / "public-comparison.json").read_text()) == result


@pytest.mark.parametrize("complete", [True, False])
def test_single_project_publication_requires_both_archives(
    publication, monkeypatch, tmp_path, complete
):
    import sys

    selected = "outerspace-apizr-oci"
    states = {
        name: {"wheel": "pending", "sdist": "pending"} for name in publication.PACKAGES
    }
    states[selected] = {
        "wheel": "public-byte-identical",
        "sdist": "public-byte-identical" if complete else "pending",
    }
    monkeypatch.setattr(publication, "stage", lambda *args: states)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_publication",
            "--dist",
            str(tmp_path),
            "--output",
            str(tmp_path / "output"),
            "--version",
            "0.4.0",
            "--require-package",
            selected,
        ],
    )
    if complete:
        publication.main()
    else:
        with pytest.raises(ValueError, match=selected):
            publication.main()
    monkeypatch.setattr(sys, "argv", [*sys.argv[:-2], "--require-complete"])
    with pytest.raises(ValueError, match="remains incomplete"):
        publication.main()


@pytest.mark.parametrize("fault", [None, "extra", "schema", "python", "bytes"])
def test_dependency_export_rejects_unrecorded_or_changed_files(
    packaging, tmp_path, monkeypatch, fault
):
    import platform

    retained = tmp_path / "candidate"
    retained.mkdir()
    candidate(retained, packaging)
    target = tmp_path / "target"
    house = target / "mcp"
    house.mkdir(parents=True)
    wheel = house / "dependency.whl"
    wheel.write_bytes(b"approved dependency")
    data = {
        "schema": "apizr.release-target/v1",
        "commit": "a" * 40,
        "candidate_sha256": packaging.digest(retained / "candidate.json"),
        "target": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "artifacts": [packaging.record(wheel, target)],
    }
    if fault == "extra":
        (house / "unapproved.whl").write_bytes(b"extra")
    elif fault == "schema":
        data["schema"] = "unknown"
    elif fault == "python":
        data["target"]["python"] = "0.0.0"
    elif fault == "bytes":
        wheel.write_bytes(b"replaced")
    packaging.write(target / "target.json", data)
    monkeypatch.setenv("APIZR_RELEASE_SET", str(retained))
    monkeypatch.setenv("APIZR_RELEASE_TARGET", str(target))
    destination = tmp_path / "proof"
    if fault:
        with pytest.raises(ValueError):
            packaging.copy_closure("mcp", destination)
        assert not destination.exists()
    else:
        assert packaging.copy_closure("mcp", destination)
        assert (destination / wheel.name).read_bytes() == wheel.read_bytes()


def test_vsix_source_admission_is_offline_without_a_checkout(
    packaging, tmp_path, monkeypatch
):
    from release_candidate_helpers import attach_editor

    from scripts.qualification.packaging import vscode_source

    attach_editor(
        tmp_path,
        {"version": "0.4.6", "commit": "a" * 40, "artifacts": []},
        packaging.ROOT,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Verifying retained VSIX bytes must not need a source checkout or fetch"
        )

    monkeypatch.setattr(vscode_source, "directory", forbidden)
    monkeypatch.setattr(vscode_source.subprocess, "run", forbidden)
    files = packaging.check_vsix(tmp_path / "editor/apizr-0.4.6.vsix", packaging.ROOT)
    assert "extension/src/extension.ts" in files

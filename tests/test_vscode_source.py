"""The engine consumes one immutable client snapshot from its dedicated owner."""

import hashlib
import json

import pytest

from scripts.qualification.packaging import vscode_source as source


@pytest.fixture
def snapshot(tmp_path):
    directory = tmp_path / ".output/vscode-source" / ("a" * 40) / "src"
    directory.mkdir(parents=True)
    (directory / "extension.ts").write_text("export const client = true;\n")
    for name, value in {
        "package.json": {"version": "0.4.6"},
        "package-lock.json": {
            "version": "0.4.6",
            "packages": {"": {"version": "0.4.6"}},
        },
        "engine.json": {"version": "0.4.6"},
    }.items():
        (directory.parent / name).write_text(json.dumps(value))
    lock = {
        "version": "0.4.6",
        "schema_version": "apizr.vscode-source/v1",
        "repository": source.REPOSITORY,
        "commit": "a" * 40,
        "files": source.inventory(directory.parent),
    }
    (tmp_path / "policy").mkdir()
    (tmp_path / source.LOCK).write_text(json.dumps(lock))
    return tmp_path


@pytest.mark.parametrize(
    "fault", [None, "edit", "add", "remove", "repository", "floating"]
)
def test_snapshot_refuses_local_forks_and_unpinned_sources(snapshot, fault):
    directory = source.directory(snapshot) / "src"
    if fault == "edit":
        (directory / "extension.ts").write_text("// independent implementation\n")
    elif fault == "add":
        (directory / "second.ts").write_text("// extra implementation\n")
    elif fault == "remove":
        (directory / "extension.ts").unlink()
    elif fault in {"repository", "floating"}:
        path = snapshot / source.LOCK
        lock = json.loads(path.read_text())
        lock["repository" if fault == "repository" else "commit"] = (
            "other" if fault == "repository" else "main"
        )
        path.write_text(json.dumps(lock))
    if fault:
        with pytest.raises(ValueError, match="(snapshot|source lock)"):
            source.verify(snapshot)
    else:
        assert (
            source.verify(snapshot)["files"]["src/extension.ts"]
            == hashlib.sha256((directory / "extension.ts").read_bytes()).hexdigest()
        )


def test_build_outputs_do_not_change_pinned_client_identity(snapshot):
    for name in ["out", "node_modules", "dist"]:
        directory = source.directory(snapshot) / name
        directory.mkdir()
        (directory / "local.js").write_text("// local build\n")
    assert source.verify(snapshot)["commit"] == "a" * 40


def test_prepared_cache_is_verified_without_fetching(snapshot, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Prepared-source verification must not access the network")

    monkeypatch.setattr(source.subprocess, "run", forbidden)
    assert source.prepare(snapshot)["commit"] == "a" * 40
    (source.directory(snapshot) / "src/extension.ts").write_text("// changed")
    with pytest.raises(ValueError, match="snapshot"):
        source.prepare(snapshot)

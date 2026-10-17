"""The engine consumes one immutable client snapshot from its dedicated owner."""

import hashlib
import json

import pytest

from scripts.qualification.packaging import vscode_source as source


@pytest.fixture
def snapshot(tmp_path):
    directory = tmp_path / "editors/vscode/src"
    directory.mkdir(parents=True)
    (directory / "extension.ts").write_text("export const client = true;\n")
    lock = {
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
    directory = snapshot / "editors/vscode/src"
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
        directory = snapshot / "editors/vscode" / name
        directory.mkdir()
        (directory / "local.js").write_text("// local build\n")
    assert source.verify(snapshot)["commit"] == "a" * 40

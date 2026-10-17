"""Explicit non-executable archive fixtures for coordinated admission tests."""

import json
import zipfile

from scripts.qualification.packaging.coordinated_distributions import record, write
from scripts.qualification.packaging.vscode_distribution import digest, manifest


def attach_editor(directory, candidate, source):
    editor = directory / "editor"
    editor.mkdir()
    package = json.loads((source / "editors/vscode/package.json").read_text())
    payload = {
        "extension/package.json": (json.dumps(package, indent=2) + "\n").encode(),
        "extension.vsixmanifest": manifest(package),
        "[Content_Types].xml": b"fixture content types",
        "extension/LICENSE": (source / "LICENSE").read_bytes(),
    }
    for name in (
        "README.md",
        "package-lock.json",
        "tsconfig.json",
        "media/icon.png",
        "engine.json",
    ):
        payload["extension/" + name] = (source / "editors/vscode" / name).read_bytes()
    for path in (source / "editors/vscode/src").glob("*.ts"):
        payload["extension/src/" + path.name] = path.read_bytes()
        payload["extension/out/" + path.stem + ".js"] = (
            b"// non-executable test fixture\n"
        )
    path = editor / f"apizr-{candidate['version']}.vsix"
    toolchain = json.loads((source / "policy/vscode-distribution.json").read_text())
    with zipfile.ZipFile(path, "w") as archive:
        for name, raw in payload.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    write(
        path.with_suffix(".json"),
        {
            "schema_version": "apizr.vscode-build/v1",
            "result": "pass",
            "vsix": path.name,
            "sha256": digest(path.read_bytes()),
            "files": {name: digest(raw) for name, raw in payload.items()},
            "source_commit": candidate["commit"],
            "source_dirty": False,
            "qualification_fixture": False,
            "repeated_build_identical": True,
            "node": "v" + toolchain["node"],
            "typescript": toolchain["typescript"],
        },
    )
    policy = json.loads((source / "policy/vscode-dependencies.json").read_text())
    write(
        editor / "dependency-licenses.json",
        {
            "result": "pass",
            "runtime_dependencies": 0,
            "packages": policy["packages"],
        },
    )
    candidate["schema"] = "apizr.release-candidate/v2"
    for item in candidate["artifacts"]:
        item["kind"] = "wheel" if item["file"].endswith(".whl") else "sdist"
    candidate["artifacts"].append({**record(path, directory), "kind": "vsix"})
    candidate["editor_evidence"] = [
        record(editor / name, directory)
        for name in (path.with_suffix(".json").name, "dependency-licenses.json")
    ]

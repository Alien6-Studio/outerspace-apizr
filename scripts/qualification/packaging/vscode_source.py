"""Pin and verify the dedicated VS Code repository's integration snapshot."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REPOSITORY = "https://github.com/Alien6-Studio/outerspace-apizr-vscode.git"
LOCK = "policy/vscode-source.json"
IGNORED = {".git", "node_modules", "out", "dist", "__pycache__", ".output"}


def inventory(directory):
    files = {}
    for parent, directories, names in os.walk(directory, followlinks=False):
        directories[:] = [name for name in directories if name not in IGNORED]
        for name in names:
            path = Path(parent) / name
            if name == ".DS_Store" or path.suffix == ".pyc":
                continue
            if path.is_symlink():
                raise ValueError("Snapshot links are not allowed")
            files[path.relative_to(directory).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return dict(sorted(files.items()))


def verify(root=ROOT):
    lock = json.loads((root / LOCK).read_text())
    if (
        lock.get("schema_version") != "apizr.vscode-source/v1"
        or lock.get("repository") != REPOSITORY
        or not re.fullmatch(r"[a-f0-9]{40}", lock.get("commit", ""))
        or not lock.get("files")
    ):
        raise ValueError("Invalid dedicated VS Code source lock")
    if inventory(root / "editors/vscode") != lock["files"]:
        raise ValueError(
            "VS Code integration snapshot differs from its dedicated source; "
            "use vscode_source sync instead of editing the snapshot"
        )
    return lock


def sync(source, commit, root=ROOT):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Select an exact VS Code source commit")

    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args])

    if git("status", "--porcelain").strip():
        raise ValueError("The dedicated source must be clean")
    if git("rev-parse", "HEAD").decode().strip() != commit:
        raise ValueError("Check out the selected source commit before syncing")
    names = git("ls-tree", "-rz", "--name-only", commit).decode().split("\0")
    payload = {}
    for name in filter(None, names):
        path = Path(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or any(part in IGNORED for part in path.parts)
        ):
            raise ValueError("Unsafe dedicated source member")
        payload[name] = git("show", f"{commit}:{name}")
    package = json.loads(payload["package.json"])
    if package["repository"]["url"] != REPOSITORY:
        raise ValueError("Source package does not identify the dedicated repository")
    target = root / "editors/vscode"
    previous = inventory(target)
    for name in previous.keys() - payload.keys():
        (target / name).unlink()
    for name, raw in payload.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    lock = {
        "schema_version": "apizr.vscode-source/v1",
        "repository": REPOSITORY,
        "commit": commit,
        "files": {
            name: hashlib.sha256(raw).hexdigest()
            for name, raw in sorted(payload.items())
        },
    }
    (root / LOCK).write_text(json.dumps(lock, indent=2) + "\n")
    return verify(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--commit")
    args = parser.parse_args()
    if bool(args.source) != bool(args.commit):
        parser.error("--source and --commit must be provided together")
    lock = sync(args.source, args.commit) if args.source else verify()
    print(
        json.dumps(
            {
                "result": "pass",
                "repository": lock["repository"],
                "commit": lock["commit"],
                "files": len(lock["files"]),
            }
        )
    )


if __name__ == "__main__":
    main()

"""Prepare a hash-verified client checkout without vendoring its source in Apizr."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
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


def read_lock(root=ROOT):
    lock = json.loads((root / LOCK).read_text())
    if (
        lock.get("schema_version") != "apizr.vscode-source/v1"
        or lock.get("repository") != REPOSITORY
        or not re.fullmatch(r"[a-f0-9]{40}", lock.get("commit", ""))
        or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", lock.get("version", ""))
        or not lock.get("files")
    ):
        raise ValueError("Invalid dedicated VS Code source lock")
    for name, sha in lock["files"].items():
        path = Path(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or any(p in IGNORED for p in path.parts)
            or not re.fullmatch(r"[a-f0-9]{64}", sha)
        ):
            raise ValueError("Invalid dedicated VS Code source member")
    return lock


def directory(root=ROOT):
    """Generated integration input; this path is never a tracked implementation."""
    return root / ".output/vscode-source" / read_lock(root)["commit"]


def verify(root=ROOT):
    lock = read_lock(root)
    target = directory(root)
    if not target.is_dir() or inventory(target) != lock["files"]:
        raise ValueError(
            "VS Code source snapshot differs or is missing; prepare its pinned checkout"
        )
    package = json.loads((target / "package.json").read_text())
    package_lock = json.loads((target / "package-lock.json").read_text())
    engine = json.loads((target / "engine.json").read_text())
    if any(
        value != lock["version"]
        for value in (
            package["version"],
            package_lock["version"],
            package_lock["packages"][""]["version"],
            engine["version"],
        )
    ):
        raise ValueError("VS Code source version differs from its lock")
    return lock


def prepare(root=ROOT):
    """Only this explicit preparation step may fetch the immutable client source."""
    lock = read_lock(root)
    if directory(root).exists():
        return verify(root)
    with tempfile.TemporaryDirectory(prefix="apizr-vscode-fetch-") as temporary:
        source = Path(temporary)
        subprocess.run(["git", "init", "--quiet", str(source)], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "fetch.fsckObjects=true",
                "fetch",
                "--quiet",
                "--depth=1",
                "--no-tags",
                REPOSITORY,
                lock["commit"],
            ],
            check=True,
            timeout=120,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "-c",
                "core.hooksPath=/dev/null",
                "checkout",
                "--quiet",
                "--detach",
                "FETCH_HEAD",
            ],
            check=True,
            timeout=30,
        )
        # sync verifies the selected revision and all declared source bytes.
        result = sync(source, lock["commit"], root, expected=lock)
    return result


def sync(source, commit, root=ROOT, *, expected=None):
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
    lock = {
        "schema_version": "apizr.vscode-source/v1",
        "repository": REPOSITORY,
        "commit": commit,
        "version": package["version"],
        "files": {
            name: hashlib.sha256(raw).hexdigest()
            for name, raw in sorted(payload.items())
        },
    }
    if expected is not None and lock != expected:
        raise ValueError("Fetched VS Code source differs from the approved lock")
    versions = (
        package["version"],
        json.loads(payload["package-lock.json"])["version"],
        json.loads(payload["package-lock.json"])["packages"][""]["version"],
        json.loads(payload["engine.json"])["version"],
    )
    if (
        len(set(versions)) != 1
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", package["version"]) is None
    ):
        raise ValueError("Uncoordinated dedicated VS Code source version")
    target = root / ".output/vscode-source" / commit
    if target.exists():
        raise ValueError(
            "Select a new source cache; existing checkouts are never overwritten"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".admit-", dir=target.parent) as temporary:
        staged = Path(temporary) / "source"
        staged.mkdir()
        for name, raw in payload.items():
            path = staged / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        staged.rename(target)
    if expected is None:
        (root / LOCK).write_text(json.dumps(lock, indent=2) + "\n")
    return verify(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--print-directory", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--commit")
    args = parser.parse_args()
    if bool(args.source) != bool(args.commit):
        parser.error("--source and --commit must be provided together")
    if args.prepare and args.source:
        parser.error("Select preparation or an explicit source update")
    lock = (
        sync(args.source, args.commit)
        if args.source
        else prepare()
        if args.prepare
        else verify()
    )
    if args.print_directory:
        print(directory())
        return
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

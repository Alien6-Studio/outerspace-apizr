"""Build once, inspect and export target-specific coordinated release artifacts.

Preparation can download locked dependencies. Verification and proof consumption
never rebuild candidates. Nothing in this module publishes a package.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

from check_distribution import check

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = {
    "outerspace-apizr": ROOT,
    "outerspace-apizr-oci": ROOT / "plugins/oci",
    "outerspace-apizr-attest": ROOT / "plugins/attest",
    "outerspace-apizr-mcp": ROOT / "plugins/mcp",
}


def run(*args, cwd=ROOT, timeout=300, env=None):
    return subprocess.run(
        list(map(str, args)),
        cwd=cwd,
        env=env,
        check=True,
        timeout=timeout,
        capture_output=True,
        text=True,
    ).stdout


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path: Path, root: Path) -> dict:
    return {
        "file": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def source_commit() -> str:
    return run("git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD").strip()


def verify_records(root: Path, records: list[dict]) -> None:
    seen = set()
    for item in records:
        relative = Path(item["file"])
        if relative.is_absolute() or ".." in relative.parts or relative in seen:
            raise ValueError("Invalid or duplicate artifact path")
        seen.add(relative)
        path = root / relative
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("Artifact links are not allowed")
        if (
            not path.is_file()
            or path.stat().st_size != item["bytes"]
            or digest(path) != item["sha256"]
        ):
            raise ValueError(f"Artifact identity mismatch: {relative}")


def load(root: Path) -> dict:
    manifest = json.loads((root / "candidate.json").read_text())
    if (
        manifest["schema"] != "apizr.release-candidate/v1"
        or manifest["commit"] != source_commit()
    ):
        raise ValueError("Candidate belongs to another source commit")
    expected = {
        name.replace("-", "_") + "-" + manifest["version"] + suffix
        for name in PROJECTS
        for suffix in ("-py3-none-any.whl", ".tar.gz")
    }
    if {Path(item["file"]).name for item in manifest["artifacts"]} != expected or len(
        manifest["artifacts"]
    ) != 8:
        raise ValueError("Expected exactly four wheels and four sdists")
    if {path.name for path in (root / "dist").iterdir()} != expected:
        raise ValueError("Unexpected distribution files")
    if {item["file"] for item in manifest["artifacts"]} != {
        "dist/" + name for name in expected
    }:
        raise ValueError("Unexpected distribution paths")
    verify_records(root, manifest["artifacts"])
    return manifest


def build(output: Path) -> None:
    if run("git", "status", "--porcelain").strip():
        raise ValueError("Candidates require a clean identified commit")
    output.mkdir(parents=True, exist_ok=False)
    dist = output / "dist"
    dist.mkdir()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    reports = []
    for name, project in PROJECTS.items():
        metadata = tomllib.loads((project / "pyproject.toml").read_text())["project"]
        if metadata["version"] != version:
            raise ValueError("Uncoordinated package versions")
        with tempfile.TemporaryDirectory(prefix="apizr-package-") as directory:
            work = Path(directory)
            archives = work / "archives"
            run("uv", "build", project, "--out-dir", archives)
            checksums = check(archives, project)
            # Reconstruction verifies sdist autonomy; it is NOT a candidate wheel.
            source = work / "sdist-source"
            source.mkdir()
            sdist = next(archives.glob("*.tar.gz"))
            with tarfile.open(sdist) as archive:
                archive.extractall(source, filter="data")
            reconstructed = work / "reconstructed"
            run(
                "uv",
                "build",
                "--wheel",
                next(source.iterdir()),
                "--out-dir",
                reconstructed,
                cwd=source,
            )
            for filename in checksums:
                path = archives / filename
                shutil.copyfile(path, dist / path.name)
            reports.append(
                {
                    "package": name,
                    "metadata": "passed",
                    "sdist_build": "passed",
                    "candidate_hashes": checksums,
                    "reconstructed_wheel_sha256": digest(
                        next(reconstructed.glob("*.whl"))
                    ),
                    "reconstruction_is_candidate": False,
                }
            )
    write(
        output / "candidate.json",
        {
            "schema": "apizr.release-candidate/v1",
            "version": version,
            "commit": source_commit(),
            "repository": "Alien6-Studio/outerspace-apizr",
            "artifacts": [record(path, output) for path in sorted(dist.iterdir())],
        },
    )
    write(output / "distribution-checks.json", reports)
    load(output)


def prepare_target(candidate: Path, output: Path) -> None:
    from smoke_oci_plugin import lock_wheels

    manifest = load(candidate)
    output.mkdir(parents=True, exist_ok=False)
    target = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "machine": platform.machine(),
        "platform": platform.platform(),
    }
    with tempfile.TemporaryDirectory(prefix="apizr-dependencies-") as directory:
        work = Path(directory)
        run(
            "uv",
            "venv",
            "--seed",
            "--no-python-downloads",
            "--python",
            sys.executable,
            work / "prepare",
        )
        for name, extras in (
            ("base", []),
            ("mcp", ["--extra", "mcp"]),
            ("extras", ["--all-extras"]),
        ):
            lock = output / (name + "-resolved.txt")
            run(
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                *extras,
                "--output-file",
                lock,
            )
            house = output / name
            house.mkdir()
            run(
                work / "prepare/bin/python",
                "-m",
                "pip",
                "download",
                "--require-hashes",
                "--only-binary=:all:",
                "--dest",
                house,
                "-r",
                lock,
                timeout=600,
            )
        core = next((candidate / "dist").glob("outerspace_apizr-*.whl"))
        for name in ("base", "mcp", "extras"):
            shutil.copyfile(core, output / name / core.name)
        for plugin, members in (
            ("oci", ("oci",)),
            ("attest", ("oci", "attest")),
            ("mcp", ("mcp",)),
        ):
            house = output / plugin
            if plugin != "mcp":
                shutil.copytree(output / "base", house)
            for member in members:
                wheel = next(
                    (candidate / "dist").glob("outerspace_apizr_" + member + "-*.whl")
                )
                shutil.copyfile(wheel, house / wheel.name)
            lock_wheels(house, output / (plugin + ".lock"))
        # Catalog export reuses the existing parser, resolver and lock validation.
        house = output / "wheelhouse"
        house.mkdir()
        for name in ("mcp", "oci", "attest"):
            for wheel in (output / name).glob("*.whl"):
                shutil.copyfile(wheel, house / wheel.name)
        run(
            "uv",
            "venv",
            "--no-python-downloads",
            "--python",
            sys.executable,
            work / "core",
        )
        run(
            "uv",
            "pip",
            "install",
            "--python",
            work / "core/bin/python",
            "--offline",
            "--no-index",
            "--find-links",
            output / "base",
            core,
        )
        run(
            work / "core/bin/python",
            "-I",
            "-B",
            ROOT / "scripts/catalog_plugin_plan.py",
            "--wheelhouse",
            house,
            "--plugin",
            "outerspace-apizr-mcp=" + str(output / "mcp.lock"),
            "--plugin",
            "outerspace-apizr-oci=" + str(output / "oci.lock"),
            "--plugin",
            "outerspace-apizr-attest=" + str(output / "attest.lock"),
            "--commit",
            manifest["commit"],
            "--output",
            output / "catalog",
            "--profile",
            "mcp",
        )
    shutil.copyfile(ROOT / "uv.lock", output / "uv.lock")
    write(
        output / "target.json",
        {
            "schema": "apizr.release-target/v1",
            "commit": manifest["commit"],
            "candidate_sha256": digest(candidate / "candidate.json"),
            "target": target,
            "artifacts": [
                record(path, output)
                for path in sorted(output.rglob("*"))
                if path.is_file()
            ],
        },
    )


def target_root() -> Path | None:
    value = os.environ.get("APIZR_RELEASE_TARGET")
    if not value:
        return None
    root = Path(value).resolve()
    candidate = Path(os.environ["APIZR_RELEASE_SET"]).resolve()
    manifest = load(candidate)
    target = json.loads((root / "target.json").read_text())
    if (
        target["schema"] != "apizr.release-target/v1"
        or target["commit"] != manifest["commit"]
        or target["candidate_sha256"] != digest(candidate / "candidate.json")
    ):
        raise ValueError("Dependency target does not belong to candidate")
    if (
        target["target"]["python"].split(".")[:2]
        != platform.python_version().split(".")[:2]
        or target["target"]["system"] != platform.system()
        or target["target"]["machine"] != platform.machine()
    ):
        raise ValueError("Dependency wheelhouse belongs to another Python/platform")
    expected = {item["file"] for item in target["artifacts"]} | {"target.json"}
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual != expected:
        raise ValueError("Unexpected dependency target files")
    verify_records(root, target["artifacts"])
    return root


def copy_closure(name: str, destination: Path) -> bool:
    """Explicit proof input: fail on mismatches, never silently fall back to building."""
    root = target_root()
    if root is None:
        if os.environ.get("APIZR_RELEASE_SET"):
            raise ValueError(
                "Candidate proofs require an explicit matching dependency target"
            )
        return False
    destination.mkdir(parents=True, exist_ok=True)
    for path in (root / name).glob("*.whl"):
        target = destination / path.name
        if target.exists() and digest(target) != digest(path):
            raise ValueError("Proof wheel conflicts with candidate")
        shutil.copyfile(path, target)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify", "target"))
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    if args.operation == "build":
        build(candidate)
    elif args.operation == "verify":
        print(json.dumps(load(candidate), indent=2))
    else:
        if args.output is None:
            parser.error("target needs --output")
        prepare_target(candidate, args.output.resolve())


if __name__ == "__main__":
    main()

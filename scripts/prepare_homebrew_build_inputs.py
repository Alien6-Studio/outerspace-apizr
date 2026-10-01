"""Fetch only reviewed, locked universal wheels for the Homebrew build group."""

import argparse
import hashlib
import io
import json
import tomllib
import urllib.parse
import urllib.request
import zipfile
from email.parser import BytesParser
from pathlib import Path

from check_dependency_sources import validate_sources
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, parse_wheel_filename

SCHEMA = "apizr.homebrew-build-inputs/v1"
MAX_BYTES = 16 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def locked_inputs(lock):
    validate_sources(lock, "outerspace-apizr")
    by_name = {}
    for package in lock["package"]:
        by_name.setdefault(package["name"], []).append(package)
    project = by_name["outerspace-apizr"][0]
    pending = list(project["dev-dependencies"]["homebrew-build"])
    selected = {}
    while pending:
        dependency = pending.pop()
        if set(dependency) != {"name"}:
            raise ValueError("Conditional or ambiguous build closure needs review")
        name = dependency["name"]
        if name in selected:
            continue
        candidates = by_name[name]
        if len(candidates) != 1:
            raise ValueError("Multiple locked build versions need review")
        package = candidates[0]
        wheels = []
        for wheel in package["wheels"]:
            filename = urllib.parse.urlsplit(wheel["url"]).path.rsplit("/", 1)[-1]
            distribution, version, _, tags = parse_wheel_filename(filename)
            if {str(tag) for tag in tags} == {"py3-none-any"}:
                if distribution != name or str(version) != package["version"]:
                    raise ValueError("Locked wheel identity mismatch")
                wheels.append(
                    {
                        "name": name,
                        "version": package["version"],
                        "filename": filename,
                        "tag": "py3-none-any",
                        "url": wheel["url"],
                        "sha256": wheel["hash"].removeprefix("sha256:"),
                    }
                )
        if len(wheels) != 1:
            raise ValueError("Exactly one reviewed universal build wheel is required")
        selected[name] = wheels[0]
        pending.extend(package.get("dependencies", []))
    return [selected[name] for name in sorted(selected)]


def manifest(lock_path, policy_path):
    lock = tomllib.loads(lock_path.read_text())
    policy = json.loads(policy_path.read_text())
    wheels = locked_inputs(lock)
    if policy["schema"] != SCHEMA or policy["build"]["distributions"] != wheels:
        raise ValueError("Build artifacts differ from reviewed Homebrew policy")
    roots = lock["package"]
    project = next(p for p in roots if p["name"] == "outerspace-apizr")
    requirements = project["metadata"]["requires-dev"]["homebrew-build"]
    if [r["name"] + r["specifier"] for r in requirements] != policy["build"]["roots"]:
        raise ValueError("Build root differs from reviewed Homebrew policy")
    return {
        "schema": SCHEMA,
        "lock_sha256": digest(lock_path.read_bytes()),
        "policy_sha256": digest(policy_path.read_bytes()),
        "build_only": True,
        "roots": policy["build"]["roots"],
        "distributions": wheels,
    }


def verify_wheel(data, item, closure):
    if digest(data) != item["sha256"]:
        raise ValueError("Build wheel SHA-256 mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        metadata_files = [
            n for n in archive.namelist() if n.endswith(".dist-info/METADATA")
        ]
        if len(metadata_files) != 1:
            raise ValueError("Ambiguous wheel metadata")
        metadata = BytesParser().parsebytes(archive.read(metadata_files[0]))
        if (canonicalize_name(metadata["Name"]), metadata["Version"]) != (
            item["name"],
            item["version"],
        ):
            raise ValueError("Build wheel metadata identity mismatch")
        for value in metadata.get_all("Requires-Dist", []):
            requirement = Requirement(value)
            # These wheels are qualified for Homebrew CPython 3.14 on both macOS architectures.
            if requirement.marker and not requirement.marker.evaluate(
                {"python_version": "3.14", "python_full_version": "3.14.0", "extra": ""}
            ):
                continue
            version = closure.get(canonicalize_name(requirement.name))
            if (
                requirement.url
                or version is None
                or version not in requirement.specifier
            ):
                raise ValueError("Wheel requires an unreviewed build dependency")


def prepare(lock_path, policy_path, output):
    evidence = manifest(lock_path, policy_path)
    output.mkdir(parents=True, exist_ok=False)
    wheelhouse = output / "build-wheelhouse"
    wheelhouse.mkdir()
    closure = {d["name"]: d["version"] for d in evidence["distributions"]}
    for item in evidence["distributions"]:
        with urllib.request.urlopen(item["url"], timeout=60) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != "https" or final.netloc != "files.pythonhosted.org":
                raise ValueError("Unreviewed artifact redirect")
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Oversized build wheel")
        verify_wheel(data, item, closure)
        (wheelhouse / item["filename"]).write_bytes(data)
    (output / "build-inputs.json").write_bytes(encoded(evidence))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.lock, args.policy, args.output)


if __name__ == "__main__":
    main()

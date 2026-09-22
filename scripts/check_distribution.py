"""Inspect both release archives and their metadata without extracting them."""

import argparse
import email.parser
import hashlib
import json
import re
import tarfile
import tomllib
import zipfile
from pathlib import Path


def check(directory: Path, project_root: Path) -> dict[str, str]:
    project = tomllib.loads((project_root / "pyproject.toml").read_text())["project"]
    readme = (project_root / project["readme"]).read_text()
    artifacts = sorted(p for p in directory.iterdir() if p.name != ".gitignore")
    expected = {
        f"outerspace_apizr-{project['version']}-py3-none-any.whl",
        f"outerspace_apizr-{project['version']}.tar.gz",
    }
    assert {p.name for p in artifacts} == expected, "Expected exactly wheel and sdist"
    for link in re.findall(r"\]\(([^)]+)\)", readme):
        assert link.startswith("https://"), f"README link is not absolute: {link}"
    digests = {}
    for artifact in artifacts:
        if artifact.suffix == ".whl":
            with zipfile.ZipFile(artifact) as archive:
                files = {name: archive.read(name) for name in archive.namelist()}
            metadata_key = next(n for n in files if n.endswith(".dist-info/METADATA"))
            assert all(
                n.startswith(
                    ("apizr/", f"outerspace_apizr-{project['version']}.dist-info/")
                )
                for n in files
            )
            assert any(n.endswith("/licenses/LICENSE") for n in files)
            assert "apizr/generators/rest/templates/preamble.txt" in files
            assert "apizr/modules/fast_apizr/generator/templates/fastApiApp.j2" in files
        else:
            with tarfile.open(artifact) as archive:
                files = {}
                for member in archive.getmembers():
                    if member.isdir():
                        continue
                    assert member.isfile(), f"Unexpected archive entry: {member.name}"
                    stream = archive.extractfile(member)
                    assert stream is not None
                    files[member.name.split("/", 1)[1]] = stream.read()
            metadata_key = "PKG-INFO"
            allowed = {
                "pyproject.toml",
                "README.md",
                "CHANGELOG.md",
                "LICENSE",
                "PKG-INFO",
                ".gitignore",  # Hatchling includes its standard VCS exclusion file.
            }
            assert all(n.startswith("src/apizr/") or n in allowed for n in files)
            assert files["README.md"].decode() == readme
            assert "src/apizr/generators/rest/templates/preamble.txt" in files
            assert "LICENSE" in files
        prefix = "" if artifact.suffix == ".whl" else "src/"
        for required in (
            "apizr/exposure/planner.py",
            "apizr/repository_interfaces/generator.py",
            "apizr/repository_interfaces/runtime.py",
            "apizr/repository_interfaces/rest_runtime.py",
            "apizr/repository_interfaces/mcp_runtime.py",
            "apizr/repository_execution/worker.py",
            "apizr/repository_execution/entrypoint.py",
            "apizr/governed_repository/embedding.py",
            "apizr/governed_repository/runtime.py",
            "apizr/subprocess_guard/filter.py",
            "apizr/subprocess_guard/entrypoint.py",
            "apizr/subprocess_guard/repository_entrypoint.py",
            "apizr/optional.py",
            "apizr/extensions/plugins/api.py",
        ):
            assert prefix + required in files, required
        for name, data in files.items():
            assert not any(
                part in {"..", "__pycache__", ".env", ".git", "tests"}
                for part in Path(name).parts
            )
            assert not name.startswith("/") and not name.endswith((".pyc", ".pyo"))
            assert b"/Users/" not in data and b"/private/tmp/" not in data, name
            assert b"-----BEGIN " + b"PRIVATE KEY-----" not in data, name
        metadata = email.parser.Parser().parsestr(files[metadata_key].decode())
        for key, value in {
            "Name": project["name"],
            "Version": project["version"],
            "Summary": project["description"],
            "License-Expression": project["license"],
            "Description-Content-Type": "text/markdown",
        }.items():
            assert metadata[key] == value, (key, metadata[key], value)
        assert set(metadata.get_all("Classifier", [])) == set(project["classifiers"])
        assert set(str(metadata["Keywords"]).split(",")) == set(project["keywords"])
        assert set(metadata.get_all("Project-URL", [])) == {
            f"{k}, {v}" for k, v in project["urls"].items()
        }
        from packaging.specifiers import SpecifierSet

        assert SpecifierSet(str(metadata["Requires-Python"])) == SpecifierSet(
            project["requires-python"]
        )
        # Compare requirement semantics, because the build backend normalizes ordering.
        from packaging.requirements import Requirement

        expected_requirements = {Requirement(v) for v in project["dependencies"]}
        extras = project.get("optional-dependencies", {})
        assert set(metadata.get_all("Provides-Extra", [])) == set(extras)
        for extra, requirements in extras.items():
            for value in requirements:
                requirement = Requirement(value)
                from packaging.markers import Marker

                marker = (
                    f'({requirement.marker}) and extra == "{extra}"'
                    if requirement.marker
                    else f'extra == "{extra}"'
                )
                requirement.marker = Marker(marker)
                expected_requirements.add(requirement)
        assert {
            Requirement(v) for v in metadata.get_all("Requires-Dist", [])
        } == expected_requirements
        payload = metadata.get_payload()
        assert isinstance(payload, str)
        assert payload.strip() == readme.strip()
        digests[artifact.name] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        print(
            f"PASS {artifact.name}: {len(files)} files; metadata, README, license and runtime resources verified"
        )
    return digests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    digests = check(args.directory, Path(__file__).resolve().parents[1])
    if args.manifest:
        args.manifest.write_text(json.dumps(digests, indent=2, sort_keys=True) + "\n")
    print(json.dumps(digests, sort_keys=True))


if __name__ == "__main__":
    main()

"""Inspect both release archives and their metadata without extracting them."""

import argparse
import email.parser
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path


def candidate_inventory(manifest):
    """Admit historical Python sets and the coordinated Python/VSIX contract."""
    schema = manifest.get("schema")
    if schema not in {"apizr.release-candidate/v1", "apizr.release-candidate/v2"}:
        raise ValueError("Unsupported candidate schema")
    version = manifest["version"]
    if (
        not isinstance(version, str)
        or re.fullmatch(r"\d+\.\d+\.\d+(?:rc[1-9]\d*)?", version) is None
    ):
        raise ValueError("Invalid candidate version")
    if tuple(map(int, version.split("rc")[0].split("."))) >= (
        0,
        4,
        6,
    ) and schema.endswith("/v1"):
        raise ValueError("Current candidates require the coordinated VSIX schema")
    python = {
        "dist/outerspace_apizr" + plugin + "-" + version + suffix
        for plugin in ("", "_oci", "_attest", "_mcp")
        for suffix in ("-py3-none-any.whl", ".tar.gz")
    }
    editor = {f"editor/apizr-{version}.vsix"} if schema.endswith("/v2") else set()
    artifacts = manifest["artifacts"]
    if (
        len(artifacts) != len(python | editor)
        or {item["file"] for item in artifacts} != python | editor
    ):
        raise ValueError("Unexpected coordinated candidate artifacts")
    if editor:
        for item in artifacts:
            expected = (
                "vsix"
                if item["file"] in editor
                else "wheel"
                if item["file"].endswith(".whl")
                else "sdist"
            )
            if item.get("kind") != expected:
                raise ValueError("Unexpected candidate artifact kind")
    return python, editor


def check_vsix(path: Path, project_root: Path) -> dict[str, str]:
    """Inspect a source-including extension without extracting or executing it."""
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 20 * 1024 * 1024
    ):
        raise ValueError("Invalid VSIX artifact")
    package = json.loads((project_root / "editors/vscode/package.json").read_bytes())
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = {item.filename for item in entries}
        if (
            len(entries) > 256
            or len(entries) != len(names)
            or sum(item.file_size for item in entries) > 20 * 1024 * 1024
        ):
            raise ValueError("Invalid VSIX inventory")
        for item in entries:
            name = Path(item.filename)
            if (
                name.is_absolute()
                or ".." in name.parts
                or (item.external_attr >> 16) & 0o170000 != 0o100000
            ):
                raise ValueError("Unsafe VSIX member")
        payload = {name: archive.read(name) for name in names}
    if json.loads(payload["extension/package.json"]) != package or package.get(
        "dependencies"
    ):
        raise ValueError("VSIX package metadata differs from source")
    expected = {
        "extension/package.json",
        "extension.vsixmanifest",
        "[Content_Types].xml",
    }
    sources = [
        ("LICENSE", project_root / "LICENSE"),
        *(
            (name, project_root / "editors/vscode" / name)
            for name in (
                "README.md",
                "package-lock.json",
                "tsconfig.json",
                "engine.json",
            )
        ),
        *(
            ("src/" + p.name, p)
            for p in sorted((project_root / "editors/vscode/src").glob("*.ts"))
        ),
    ]
    extension = project_root / "editors/vscode"
    for asset in sorted((extension / "media").rglob("*")):
        if asset.is_file():
            if asset.is_symlink() or asset.suffix not in {".png", ".gif"}:
                raise ValueError("Invalid VSIX media source")
            sources.append((asset.relative_to(extension).as_posix(), asset))
    if not any(name.startswith("src/") for name, _ in sources):
        raise ValueError("Missing extension source inventory")
    for name, source in sources:
        member = "extension/" + name
        expected.add(member)
        if payload.get(member) != source.read_bytes():
            raise ValueError("VSIX source/notice differs: " + name)
        if name.startswith("src/"):
            expected.add("extension/out/" + Path(name).stem + ".js")
    from scripts.qualification.packaging.vscode_distribution import manifest

    if names != expected or payload["extension.vsixmanifest"] != manifest(package):
        raise ValueError("Unexpected VSIX files or manifest")
    return {
        name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(payload.items())
    }


def check(directory: Path, project_root: Path) -> dict[str, str]:
    project = tomllib.loads((project_root / "pyproject.toml").read_text())["project"]
    readme = (project_root / project["readme"]).read_text()
    artifacts = sorted(p for p in directory.iterdir() if p.name != ".gitignore")
    stem = project["name"].replace("-", "_")
    core = stem == "outerspace_apizr"
    package = "apizr" if core else stem.removeprefix("outerspace_")
    expected = {
        f"{stem}-{project['version']}-py3-none-any.whl",
        f"{stem}-{project['version']}.tar.gz",
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
                    (
                        package + "/",
                        f"{stem}-{project['version']}.dist-info/",
                        *(() if core else ("apizr-extension.json",)),
                    )
                )
                for n in files
            )
            assert any(n.endswith("/licenses/LICENSE") for n in files)
            if core:
                assert "apizr/generators/rest/templates/preamble.txt" in files
            else:
                assert json.loads(files["apizr-extension.json"]) == json.loads(
                    (project_root / "apizr-extension.json").read_bytes()
                )
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
            if not core:
                allowed.add("apizr-extension.json")
                assert json.loads(files["apizr-extension.json"]) == json.loads(
                    (project_root / "apizr-extension.json").read_bytes()
                )
            assert all(
                n.startswith("src/" + package + "/") or n in allowed for n in files
            )
            assert files["README.md"].decode() == readme
            if core:
                assert "src/apizr/generators/rest/templates/preamble.txt" in files
            assert "LICENSE" in files
        prefix = "" if artifact.suffix == ".whl" else "src/"
        for required in (
            (
                "apizr/py.typed",
                "apizr/exposure/planner.py",
                "apizr/experiments/__init__.py",
                "apizr/experiments/model.py",
                "apizr/experiments/inputs.py",
                "apizr/experiments/_lexical.py",
                "apizr/experiments/_files.py",
                "apizr/experiments/metrics.py",
                "apizr/experiments/outputs.py",
                "apizr/experiments/randomness.py",
                "apizr/experiments/environment.py",
                "apizr/experiments/serialization.py",
                "apizr/experiments/values.py",
                "apizr/experiments/parameters.py",
                "apizr/experiments/notebook_source.py",
                "apizr/experiments/provider_source.py",
                "apizr/scientific_providers/__init__.py",
                "apizr/scientific_providers/admission.py",
                "apizr/scientific_providers/contracts/__init__.py",
                "apizr/scientific_providers/contracts/model.py",
                "apizr/scientific_providers/contracts/selection.py",
                "apizr/scientific_providers/selection/__init__.py",
                "apizr/scientific_providers/selection/operations.py",
                "apizr/experiments/source_analysis.py",
                "apizr/readiness/analysis.py",
                "apizr/scientific_providers/contracts/admission.py",
                "apizr/scientific_providers/builtin/__init__.py",
                "apizr/scientific_providers/builtin/provider.py",
                "apizr/scientific_providers/builtin/recognition.py",
                "apizr/scientific_providers/builtin/metrics.py",
                "apizr/scientific_providers/builtin/outputs.py",
                "apizr/scientific_providers/builtin/inputs.py",
                "apizr/scientific_providers/builtin/randomness.py",
                "apizr/scientific_providers/builtin/locations.py",
                "apizr/experiments/inspection.py",
                "apizr/experiments/planning.py",
                "apizr/experiments/bindings.py",
                "apizr/experiments/run_protocol.py",
                "apizr/experiments/runner.py",
                "apizr/experiments/worker.py",
                "apizr/experiments/store.py",
                "apizr/experiments/history.py",
                "apizr/experiments/comparison.py",
                "apizr/experiments/comparison_reporting.py",
                "apizr/experiments/inspection_model.py",
                "apizr/experiments/reporting.py",
                "apizr/cli/commands/experiment.py",
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
                "apizr/plugins/artifacts/__init__.py",
                "apizr/plugins/artifacts/models.py",
                "apizr/plugins/artifacts/wheel.py",
                "apizr/plugins/artifacts/_download_worker.py",
                "apizr/plugins/artifacts/requirements.py",
                "apizr/contracts/analysis.py",
                "apizr/contracts/application.py",
                "apizr/contracts/json.py",
                "apizr/contracts/lowering.py",
                "apizr/contracts/types.py",
                "apizr/contracts/delivery.py",
                "apizr/contracts/results.py",
                "apizr/contracts/distribution.py",
                "apizr/contracts/publication.py",
                "apizr/environment/extras.py",
                "apizr/environment/python_target.py",
                "apizr/workspace/analysis_session.py",
                "apizr/workspace/application_resources.py",
                "apizr/workspace/compiler.py",
                "apizr/workspace/mcp_session.py",
                "apizr/workspace/operator_policy.py",
                "apizr/workspace/verification.py",
                "apizr/workspace/source_access.py",
                "apizr/generators/notebooks.py",
                "apizr/notebooks/exporter.py",
                "apizr/notebooks/configuration.py",
                "apizr/capabilities/inspection.py",
                "apizr/interfaces/files.py",
            )
            if core
            else (package + "/__init__.py",)
        ):
            assert prefix + required in files, required
        if core:
            assert not any(
                name.startswith(prefix + "apizr/")
                and name.endswith(".py")
                and "/" not in name.removeprefix(prefix + "apizr/")
                and name != prefix + "apizr/__init__.py"
                for name in files
            ), "Core root contains a retired facade or implementation"
            assert not any(
                name.startswith(
                    tuple(
                        prefix + "apizr/" + retired + "/"
                        for retired in ("modules", "legacy", "extensions")
                    )
                )
                for name in files
            )
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
        assert set(metadata.get_all("Classifier", [])) == set(
            project.get("classifiers", [])
        )
        if core:
            assert set(str(metadata["Keywords"]).split(",")) == set(project["keywords"])
        assert set(metadata.get_all("Project-URL", [])) == {
            f"{k}, {v}" for k, v in project.get("urls", {}).items()
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
        if artifact.suffix == ".whl":
            import configparser

            key = f"{stem}-{project['version']}.dist-info/entry_points.txt"
            entries = configparser.ConfigParser()
            if key in files:
                entries.read_string(files[key].decode())
            actual = (
                dict(entries["console_scripts"])
                if entries.has_section("console_scripts")
                else {}
            )
            assert actual == project.get("scripts", {}), "Unexpected entry points"
        if not core:
            manifest = json.loads(files["apizr-extension.json"])
            assert manifest["name"] == project["name"]
            assert manifest["version"] == project["version"]
            assert manifest["protocol"] == "apizr.extension/v1"
        payload = metadata.get_payload()
        assert isinstance(payload, str)
        assert payload.strip() == readme.strip()
        digests[artifact.name] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        print(
            f"PASS {artifact.name}: {len(files)} files; metadata, README, license and runtime resources verified"
        )
    return digests


def check_coordinated(directory: Path, project_root: Path) -> dict[str, str]:
    projects = [
        project_root,
        *(project_root / "plugins" / name for name in ("oci", "attest", "mcp")),
    ]
    digests = {}
    version = tomllib.loads((project_root / "pyproject.toml").read_text())["project"][
        "version"
    ]
    for root in projects:
        project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
        assert project["version"] == version
        prefix = project["name"].replace("-", "_") + "-" + version
        with tempfile.TemporaryDirectory() as temporary:
            selected = Path(temporary)
            for suffix in ("-py3-none-any.whl", ".tar.gz"):
                source = directory / (prefix + suffix)
                assert source.is_file() and not source.is_symlink()
                shutil.copyfile(source, selected / source.name)
            digests.update(check(selected, root))
    assert {path.name for path in directory.iterdir()} == set(digests), (
        "Unexpected distribution files"
    )
    return digests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--coordinated", action="store_true")
    parser.add_argument(
        "--vsix", type=Path, help="Also inspect the coordinated extension"
    )
    args = parser.parse_args()
    inspect = check_coordinated if args.coordinated else check
    digests = inspect(args.directory, Path(__file__).resolve().parents[3])
    if args.vsix:
        check_vsix(args.vsix, Path(__file__).resolve().parents[3])
        digests[args.vsix.name] = hashlib.sha256(args.vsix.read_bytes()).hexdigest()
    if args.manifest:
        args.manifest.write_text(json.dumps(digests, indent=2, sort_keys=True) + "\n")
    print(json.dumps(digests, sort_keys=True))


if __name__ == "__main__":
    main()

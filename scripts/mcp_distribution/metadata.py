"""Static distribution identity and registry installation contracts."""

import hashlib
import json
import re
import tomllib
from pathlib import Path

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "Alien6-Studio/outerspace-apizr"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
NAME = "io.github.Alien6-Studio/outerspace-apizr"
PACKAGES = ("outerspace-apizr", "outerspace-apizr-mcp")
FLAGS = ("--project", "--operator-policy", "--plugins-dir")


def read(path: Path):
    return json.loads(path.read_text())


def validate_metadata(root: Path = ROOT) -> dict:
    fixtures = root / "tests/fixtures/mcp_distribution"
    for filename, origin in read(fixtures / "origins.json").items():
        assert (
            hashlib.sha256((fixtures / filename).read_bytes()).hexdigest()
            == origin["sha256"]
        )
    descriptor = read(root / "server.json")
    Draft7Validator(read(fixtures / "registry-schema.json")).validate(descriptor)
    Draft7Validator(read(fixtures / "glama-schema.json")).validate(
        read(root / "glama.json")
    )
    plugin = tomllib.loads((root / "plugins/mcp/pyproject.toml").read_text())["project"]
    core = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    assert descriptor["version"] == plugin["version"] == core["version"]
    assert descriptor["name"] == NAME and descriptor["title"] == "OuterSpace Apizr"
    assert descriptor["repository"] == {
        "url": REPOSITORY_URL,
        "source": "github",
        "subfolder": "plugins/mcp",
    }
    assert (
        descriptor["websiteUrl"]
        == "https://apizr.outerspace.sh/reference/apizr-mcp-server/"
    )
    assert (
        descriptor["icons"][0]["src"]
        == "https://apizr.outerspace.sh/assets/images/logo.png"
    )
    assert not descriptor.get("remotes")
    (package,) = descriptor["packages"]
    assert (
        package["registryType"] == "pypi"
        and package["registryBaseUrl"] == "https://pypi.org"
    )
    assert package["identifier"] == plugin["name"] == PACKAGES[1]
    assert package["version"] == descriptor["version"]
    assert package["runtimeHint"] == "uvx" and package["transport"] == {"type": "stdio"}
    assert not package.get("environmentVariables") and not package.get(
        "runtimeArguments"
    )
    assert plugin["scripts"][PACKAGES[1]] == "apizr_mcp.launcher:main"
    assert f"<!-- mcp-name: {NAME} -->" in (root / "plugins/mcp/README.md").read_text()
    assert f"outerspace-apizr=={core['version']}" in plugin["dependencies"]
    arguments = package["packageArguments"]
    assert tuple(a["name"] for a in arguments) == FLAGS
    for argument in arguments:
        assert argument["isRequired"] is True and argument["type"] == "named"
        assert argument["format"] == "filepath" and "default" not in argument
        assert "Registry installation guide" in argument["description"]
        assert len(argument["description"].split()) >= 20
        assert "/Users/" not in argument["description"]
    return descriptor


def candidate_artifacts(candidate: dict, version: str, source_sha: str) -> dict:
    """Bind exact release archives, not merely the latest versions on an index."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("A complete reviewed source SHA is required")
    if any(
        candidate.get(k) != v
        for k, v in {
            "schema": "apizr.release-candidate/v1",
            "repository": REPOSITORY,
            "version": version,
            "commit": source_sha,
        }.items()
    ):
        raise ValueError("Candidate identity mismatch")
    expected = {}
    for name in PACKAGES:
        filenames = {
            name.replace("-", "_") + "-" + version + suffix
            for suffix in ("-py3-none-any.whl", ".tar.gz")
        }
        selected = {}
        for artifact in candidate["artifacts"]:
            path = Path(artifact["file"])
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Invalid artifact path")
            if path.name in filenames:
                if path.name in selected or not re.fullmatch(
                    r"[0-9a-f]{64}", artifact["sha256"]
                ):
                    raise ValueError("Invalid or duplicate artifact digest")
                selected[path.name] = artifact["sha256"]
        if selected.keys() != filenames:
            raise ValueError("Both qualified wheel and sdist are required")
        expected[name] = selected
    return expected

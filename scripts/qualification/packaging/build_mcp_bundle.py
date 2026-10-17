"""Build a deterministic local MCPB for later, separately authorized submission."""

import argparse
import hashlib
import json
import tomllib
import zipfile
from pathlib import Path

from jsonschema import Draft7Validator

from scripts.mcp_distribution.metadata import ROOT, read, validate_metadata


def build(output: Path, root: Path = ROOT) -> dict:
    descriptor = validate_metadata(root)
    source = root / "plugins/mcp/distribution"
    manifest = read(source / "manifest.json")
    Draft7Validator(
        read(root / "tests/fixtures/mcp_distribution/mcpb-schema.json")
    ).validate(manifest)
    configuration = tomllib.loads((source / "pyproject.toml").read_text())
    project = configuration["project"]
    assert manifest["version"] == project["version"] == descriptor["version"]
    assert project["dependencies"] == [f"outerspace-apizr-mcp=={descriptor['version']}"]
    assert manifest["server"]["type"] == "uv"
    assert manifest["server"]["entry_point"] == "src/server.py"
    assert manifest["compatibility"]["platforms"] == ["darwin", "linux"]
    assert configuration["tool"]["uv"] == {
        "package": False,
        "environments": ["sys_platform == 'darwin'", "sys_platform == 'linux'"],
    }
    config = manifest["user_config"]
    assert set(config) == {"project", "operator_policy", "plugins_dir"}
    for value in config.values():
        assert value["required"] is True and "default" not in value
        assert "Registry installation guide" in value["description"]
    args = ["run", "--directory", "${__dirname}", "src/server.py"]
    for flag in ("--project", "--operator-policy", "--plugins-dir"):
        args.extend([flag, "${user_config." + flag[2:].replace("-", "_") + "}"])
    assert manifest["server"]["mcp_config"] == {"command": "uv", "args": args}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Explicit allowlist: no environment, credentials, generated venv or host paths.
    entries = {
        name: (source / name).read_bytes()
        for name in ("manifest.json", "pyproject.toml", "src/server.py")
    }
    entries["LICENSE"] = (root / "plugins/mcp/LICENSE").read_bytes()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return {
        "version": manifest["version"],
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "files": sorted(entries),
        "published": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(build(parser.parse_args().output), indent=2))

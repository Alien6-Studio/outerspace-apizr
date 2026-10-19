"""Exercise the registry command from local wheels, without publishing a package."""

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from email.parser import BytesParser
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters

from scripts.mcp_distribution.metadata import validate_metadata
from scripts.qualification.interfaces.mcp_schema_proof import (
    discovery,
    verify_discovery_contract,
    verify_guidance,
    write,
)
from scripts.qualification.interfaces.mcp_tool_metadata import review, validate_result
from scripts.qualification.packaging.build_mcp_bundle import build

REPO = Path(__file__).resolve().parents[3]


def documented_inputs(root: Path, store: str) -> dict:
    """A new user's project/grant comes only from the websiteUrl documentation."""
    guide = (
        REPO / "tests/fixtures/qualified-guides/reference/apizr-mcp-server.md"
    ).read_text()
    examples = dict(
        re.findall(
            r"<!-- registry-fixture:([^ ]+) -->\n```\w+\n(.*?)\n```", guide, re.DOTALL
        )
    )
    expected = {
        "apizr.toml",
        "src/calculator.py",
        "policies/readiness.json",
        "policies/exposure.json",
        "operator.json",
    }
    assert set(examples) == expected
    project = root / "registry-new-user"
    for name, contents in examples.items():
        target = project / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            contents.replace("<ABSOLUTE_PROJECT_ROOT>", str(project.resolve())) + "\n"
        )
    return {
        "--project": str(project / "apizr.toml"),
        "--operator-policy": str(project / "operator.json"),
        "--plugins-dir": store,
    }


async def inspect_client(client, root: Path, label: str):
    tools = [
        tool.model_dump(mode="json", by_alias=True)
        for tool in (await client.list_tools()).tools
    ]
    metadata = discovery(client, tools)
    verify_guidance(metadata)
    verify_discovery_contract(metadata)
    write(root / f"registry-discovery-{label}.json", metadata)
    write(root / f"registry-tool-review-{label}.json", review(metadata))
    history_arguments = {
        "apizr_experiment_list": {},
        "apizr_experiment_show": {"run_id": "0" * 64},
        "apizr_experiment_diff": {"run_a": "0" * 64, "run_b": "1" * 64},
    }
    refusals = {}
    for tool in tools:
        name = tool["name"]
        result = await client.call_tool(name, history_arguments.get(name, {}))
        if name in history_arguments:
            # The documented new-user policy grants source analysis only.
            assert result.is_error
            code = result.structured_content["error"]["code"]
            assert code == "operator_operation_denied"
            refusals[name] = code
        else:
            validate_result(tool, result)
    assert set(refusals) == set(history_arguments)
    write(root / f"registry-history-refusals-{label}.json", refusals)


async def main(root: Path):
    config = json.loads((root / "installed.json").read_text())
    descriptor = validate_metadata()
    package = descriptor["packages"][0]
    assert package["runtimeHint"] == "uvx"
    assert package["transport"] == {"type": "stdio"}
    uvx = shutil.which("uvx")
    assert uvx is not None
    wheel = next((root / "wheels").glob("outerspace_apizr_mcp-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        metadata = BytesParser().parsebytes(
            archive.read(
                next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
            )
        )
        assert f"<!-- mcp-name: {descriptor['name']} -->" in metadata.get_payload()
    # Substitute only the unpublished package source. Everything after the
    # executable name comes from the committed descriptor and operator inputs.
    prefix = [
        "--isolated",
        "--offline",
        "--no-index",
        "--find-links",
        str(root / "wheels"),
        "--python",
        str(root / "client/bin/python"),
        "--from",
        str(wheel),
        package["identifier"],
    ]
    values = documented_inputs(root, config["store"])
    arguments = []
    for argument in package["packageArguments"]:
        assert argument["type"] == "named" and argument["isRequired"]
        arguments.extend([argument["name"], values[argument["name"]]])
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for mode in ("auto", "legacy"):
        async with Client(
            StdioServerParameters(command=uvx, args=prefix + arguments, env=env),
            mode=mode,
            read_timeout_seconds=30,
        ) as client:
            await inspect_client(client, root, "uvx-" + mode)
    invalid_policy = root / "registry-invalid-policy.json"
    invalid_policy.write_text("{invalid JSON}")
    for flag, replacement, expected in (
        ("--project", None, "--project"),
        ("--project", "relative/apizr.toml", "absolute_project_required"),
        ("--operator-policy", None, "operator_policy_required"),
        ("--operator-policy", str(invalid_policy), "operator_policy_invalid"),
        ("--plugins-dir", str(root / "registry-absent-store"), "plugin_not_installed"),
    ):
        denied = arguments.copy()
        index = denied.index(flag)
        if replacement is None:
            del denied[index : index + 2]
        else:
            denied[index + 1] = replacement
        result = subprocess.run(
            [uvx, *prefix, *denied],
            input=b"",
            capture_output=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 2 and not result.stdout, result
        assert expected.encode() in result.stderr, result.stderr
    assert not (root / "registry-absent-store").exists()
    bundle = root / "outerspace-apizr-0.4.6.mcpb"
    bundle_report = build(bundle)
    extracted = root / "registry-bundle"
    extracted.mkdir(exist_ok=True)
    with zipfile.ZipFile(bundle) as archive:
        assert set(archive.namelist()) == set(bundle_report["files"])
        for name in ("manifest.json", "pyproject.toml", "src/server.py", "LICENSE"):
            target = extracted / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    manifest = json.loads((extracted / "manifest.json").read_text())
    substitutions = {"${__dirname}": str(extracted)}
    substitutions.update(
        {
            "${user_config." + key[2:].replace("-", "_") + "}": value
            for key, value in values.items()
        }
    )
    bundle_args = []
    for arg in manifest["server"]["mcp_config"]["args"]:
        value = substitutions.get(arg, arg)
        assert isinstance(value, str)
        bundle_args.append(value)
    assert not any("${" in arg for arg in bundle_args)
    bundle_env = {
        "PATH": os.environ.get("PATH", ""),
        "UV_OFFLINE": "1",
        "UV_NO_INDEX": "1",
        "UV_FIND_LINKS": str(root / "wheels"),
        "UV_PYTHON": str(root / "client/bin/python"),
        "UV_PYTHON_DOWNLOADS": "never",
        "UV_CACHE_DIR": str(root / "registry-uv-cache"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    uv = shutil.which(manifest["server"]["mcp_config"]["command"])
    assert uv is not None
    # The retained wheelhouse contains this exact native target, not every
    # Python/platform needed by uv's universal project lock. Prepare the bundle's
    # runtime offline from its unchanged dependency declaration, then launch it
    # without re-resolving public packages that do not exist before release.
    subprocess.run(
        [
            uv,
            "venv",
            "--python",
            str(root / "client/bin/python"),
            str(extracted / ".venv"),
        ],
        env=bundle_env,
        check=True,
        timeout=60,
    )
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(extracted / ".venv/bin/python"),
            "--only-binary",
            ":all:",
            "-r",
            str(extracted / "pyproject.toml"),
        ],
        env=bundle_env,
        check=True,
        timeout=60,
    )
    bundle_env["UV_NO_SYNC"] = "1"
    for mode in ("auto", "legacy"):
        async with Client(
            StdioServerParameters(
                command=uv, args=bundle_args, env=bundle_env, cwd=root
            ),
            mode=mode,
            read_timeout_seconds=60,
        ) as client:
            await inspect_client(client, root, "mcpb-" + mode)
    write(root / "mcpb-proof.json", bundle_report)
    report = {
        "success": True,
        "source": "local 0.4.6 candidate wheels; no public package or directory mutation",
        "protocol_modes": ["auto", "legacy"],
        "read_only_tools": 6,
        "history_requires_explicit_authority": True,
        "policy_and_installation_refusals": True,
        "documented_new_user_inputs": True,
        "titles_schemas_annotations": True,
        "mcpb_offline_launch": True,
    }
    (root / "registry-launch.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS registry uvx launcher, six read-only tools, policy/store refusals")


if __name__ == "__main__":
    anyio.run(main, Path(sys.argv[1]))

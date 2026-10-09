"""Prove the secure locked MCP dependency refuses macOS Intel without a build.

cryptography >=49 no longer publishes Intel macOS wheels. Versions with Intel
wheels have known vulnerabilities, so they are not substituted for the lock.
This is an installed artifact-compatibility refusal, not a successful MCP session.
"""

import argparse
import hashlib
import json
import platform
import sys
import tomllib
from pathlib import Path

from smoke_mcp_server import REPO, run


def prove(root: Path, python: str) -> None:
    assert platform.system() == "Darwin" and platform.machine() == "x86_64"
    assert sys.version_info[:2] == (3, 14)
    root.mkdir(parents=True, exist_ok=False)
    house = root / "wheels"
    house.mkdir()
    for project in (REPO, REPO / "plugins/mcp"):
        run(["uv", "build", "--wheel", project, "--out-dir", house], root)
    (core,) = house.glob("outerspace_apizr-*.whl")
    (plugin,) = house.glob("outerspace_apizr_mcp-*.whl")
    run(
        [
            "uv",
            "export",
            "--locked",
            "--no-default-groups",
            "--extra",
            "preparation",
            "--no-emit-project",
            "--output-file",
            root / "base.lock",
        ],
        REPO,
    )
    env = root / "preparer"
    run(["uv", "venv", "--no-python-downloads", "--python", python, env], root)
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            env / "bin/python",
            "--require-hashes",
            "--only-binary",
            ":all:",
            "-r",
            root / "base.lock",
        ],
        root,
    )
    run(
        ["uv", "pip", "install", "--python", env / "bin/python", "--no-deps", core],
        root,
    )
    locked = tomllib.loads((REPO / "uv.lock").read_text())
    packages = {p["name"]: p for p in locked["package"]}
    assert {"name": "pyjwt", "extra": ["crypto"]} in packages["mcp"]["dependencies"]
    assert {"name": "cryptography"} in packages["pyjwt"]["optional-dependencies"][
        "crypto"
    ]
    crypto = packages["cryptography"]
    # Preserve every reviewed wheel hash. The selected artifact must still match
    # this native interpreter; hash admission alone does not make it compatible.
    crypto_hashes = sorted({w["hash"] for w in crypto["wheels"]})
    version = tomllib.loads((REPO / "plugins/mcp/pyproject.toml").read_text())[
        "project"
    ]["version"]
    pins = root / "admitted.lock"
    pins.write_text(
        f"cryptography=={crypto['version']} "
        + " ".join("--hash=" + value for value in crypto_hashes)
        + f"\nouterspace-apizr-mcp=={version} --hash=sha256:"
        + hashlib.sha256(plugin.read_bytes()).hexdigest()
        + "\n"
    )
    output = root / "prepared"
    result = json.loads(
        run(
            [
                env / "bin/apizr",
                "plugins",
                "prepare",
                "outerspace-apizr-mcp",
                "--version",
                version,
                "--python",
                env / "bin/python",
                "--platform",
                "native",
                "--wheelhouse",
                house,
                "--index-url",
                "https://pypi.org/simple",
                "--requirements",
                pins,
                "--output-dir",
                output,
                "--json",
            ],
            root,
            expected=2,
        )
    )
    (root / "refusal.json").write_text(json.dumps(result, indent=2) + "\n")
    assert result["state"] == "refused", result
    diagnostic = result["diagnostics"][0]
    assert diagnostic["reason"] == "compatible_wheel_unavailable", result
    assert diagnostic["distribution"] == "cryptography", result
    assert diagnostic["version"] == crypto["version"], result
    assert result["target"]["python"].startswith("3.14."), result
    assert result["target"]["machine"] == "x86_64", result
    assert result["installation"] == result["activation"] == "not_performed"
    assert not output.exists() and not list(root.glob(".apizr-preparation-*"))
    (root / "proof.json").write_text(
        json.dumps(
            {
                "commit": run(["git", "rev-parse", "HEAD"], REPO).strip(),
                "candidate_sha256": hashlib.sha256(core.read_bytes()).hexdigest(),
                "interpreter": python,
                "target": result["target"],
                "locked_distribution": f"cryptography=={crypto['version']}",
                "dependency_chain": ["mcp", "pyjwt[crypto]", "cryptography"],
                "refused_incompatible_admitted_wheels": True,
                "installation": "not_performed",
                "activation": "not_performed",
                "mcp_stdio": "unavailable_for_secure_locked_intel_closure",
                "output_and_staging_absent": True,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prove(args.output.resolve(), sys.executable)

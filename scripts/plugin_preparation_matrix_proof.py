"""Qualify native core resolution and three plugin preparations outside checkout.

Build candidate wheels once, download only the hash-locked native dependency
closure, then use the installed candidate with no index. Serving and publication
are separate qualifications. Intel MCP's unavailable secure closure is proved by
plugin_preparation_intel_proof.py rather than replaced with an older dependency.
"""

import argparse
import hashlib
import json
import os
import platform
import sys
import tomllib
from pathlib import Path

from smoke_extension_packaging import snapshot
from smoke_mcp_server import REPO, run


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prove(root: Path, python: str, without_mcp: bool, expect_glibc: str | None) -> None:
    if root.is_relative_to(REPO) or REPO.is_relative_to(root):
        raise ValueError("Use a new workspace outside checkout")
    if without_mcp:
        assert platform.system() == "Darwin" and platform.machine() == "x86_64"
    if expect_glibc:
        assert platform.libc_ver() == ("glibc", expect_glibc), platform.libc_ver()
    root.mkdir(parents=True, exist_ok=False)
    house = root / "wheels"
    house.mkdir()
    for project in (REPO, *(REPO / "plugins" / p for p in ("mcp", "oci", "attest"))):
        run(["uv", "build", "--wheel", project, "--out-dir", house], root)
    (core,) = house.glob("outerspace_apizr-*.whl")
    version = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]
    seed = root / "download"
    run(
        ["uv", "venv", "--seed", "--no-python-downloads", "--python", python, seed],
        root,
    )
    for name, extras in (
        ("base", ["--extra", "preparation"]),
        *(
            ([("mcp", ["--extra", "mcp", "--extra", "preparation"])])
            if not without_mcp
            else []
        ),
    ):
        lock = root / (name + ".lock")
        run(
            [
                "uv",
                "export",
                "--locked",
                "--no-default-groups",
                "--no-emit-project",
                *extras,
                "--output-file",
                lock,
            ],
            REPO,
        )
        run(
            [
                seed / "bin/python",
                "-m",
                "pip",
                "download",
                "--require-hashes",
                "--only-binary=:all:",
                "--dest",
                house,
                "-r",
                lock,
            ],
            root,
        )
    preparer = root / "preparer"
    run(["uv", "venv", "--no-python-downloads", "--python", python, preparer], root)
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            preparer / "bin/python",
            "--offline",
            "--no-index",
            "--find-links",
            house,
            "--require-hashes",
            "--only-binary",
            ":all:",
            "-r",
            root / "base.lock",
        ],
        root,
    )
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            preparer / "bin/python",
            "--no-deps",
            core,
        ],
        root,
    )
    driver = root / "core_resolution.py"
    driver.write_text("""import json, sys, tempfile, time
from pathlib import Path
import apizr
from apizr.plugins.preparation.models import Control
from apizr.plugins.preparation.target import probe
from apizr.plugins.preparation.resolver import configure, resolve
assert not Path(apizr.__file__).resolve().is_relative_to(Path(sys.argv[3]))
with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
    work = Path(directory)
    control = Control(time.monotonic() + 120)
    target = probe(Path(sys.executable), "native", work, control)
    tool = configure(None, Path(sys.executable), target, Path(sys.argv[1]), None, work, control)
    pins = resolve(tool, "outerspace-apizr", sys.argv[2], work, control)
    print(json.dumps({"resolver": tool.version, "resolver_platform": target.resolver_platform,
        "target": target.identity.model_dump(mode="json"),
        "pins": [pin.model_dump(mode="json") for pin in pins]}))
""")
    core_evidence = json.loads(
        run([preparer / "bin/python", "-I", "-B", driver, house, version, REPO], root)
    )
    locked = {
        p["name"]: p["version"]
        for p in tomllib.loads((REPO / "uv.lock").read_text())["package"]
    }
    for profile in ("mcp", "oci", "attest"):
        project = tomllib.loads(
            (REPO / "plugins" / profile / "pyproject.toml").read_text()
        )["project"]
        assert project["version"] == version
        locked[project["name"]] = version
    for pin in core_evidence["pins"]:
        assert locked[pin["name"]] == pin["version"]
        (wheel,) = house.glob(
            pin["name"].replace("-", "_") + "-" + pin["version"] + "-*.whl"
        )
        assert digest(wheel) in pin["hashes"]
    (root / "core-resolution.json").write_text(
        json.dumps(core_evidence, indent=2) + "\n"
    )
    before = snapshot(preparer)
    global_state = root / "global-plugin-state"
    global_state.mkdir()
    (global_state / "sentinel").write_text("unchanged\n")
    global_before = snapshot(global_state)
    env = {
        **os.environ,
        "XDG_DATA_HOME": str(global_state),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    results = {}
    profiles = ["oci", "attest", *([] if without_mcp else ["mcp"])]
    for profile in profiles:
        output = root / ("prepared-" + profile)
        result = json.loads(
            run(
                [
                    preparer / "bin/apizr",
                    "plugins",
                    "prepare",
                    "outerspace-apizr-" + profile,
                    "--version",
                    version,
                    "--python",
                    preparer / "bin/python",
                    "--platform",
                    "native",
                    "--wheelhouse",
                    house,
                    "--output-dir",
                    output,
                    "--json",
                ],
                root,
                env=env,
            )
        )
        assert result["state"] == "prepared", result
        assert result["resolver"] == core_evidence["resolver"]
        assert result["resolver_platform"] == core_evidence["resolver_platform"]
        assert result["installation"] == result["activation"] == "not_performed"
        assert not list((output / "profile").iterdir())
        assert json.loads((output / "preparation.json").read_text()) == result
        expected = ""
        for artifact in result["artifacts"]:
            actual = digest(output / "wheelhouse" / artifact["filename"])
            assert (
                actual == artifact["sha256"] and actual in artifact["admitted_hashes"]
            )
            assert locked[artifact["name"]] == artifact["version"]
            expected += (
                f"{artifact['name']}=={artifact['version']} --hash=sha256:{actual}\n"
            )
        assert (output / "requirements.lock").read_text() == expected
        results[profile] = {
            "state": "prepared",
            "artifacts": len(result["artifacts"]),
            "manifest_sha256": digest(output / "preparation.json"),
        }
    assert snapshot(preparer) == before
    assert snapshot(global_state) == global_before
    if without_mcp:
        run(
            [
                python,
                REPO / "scripts/plugin_preparation_intel_proof.py",
                "--output",
                root / "intel-mcp-refusal",
                "--candidate-wheels",
                house,
            ],
            root,
            timeout=600,
        )
        results["mcp"] = {
            "state": "refused",
            "reason": "compatible_wheel_unavailable",
            "evidence": "intel-mcp-refusal/proof.json",
        }
    assert not list(root.glob(".apizr-preparation-*"))
    (root / "proof.json").write_text(
        json.dumps(
            {
                "commit": run(
                    ["git", "-c", f"safe.directory={REPO}", "rev-parse", "HEAD"], REPO
                ).strip(),
                "worktree_dirty": bool(
                    run(
                        [
                            "git",
                            "-c",
                            f"safe.directory={REPO}",
                            "status",
                            "--porcelain",
                        ],
                        REPO,
                    ).strip()
                ),
                "resolver": core_evidence["resolver"],
                "resolver_platform": core_evidence["resolver_platform"],
                "target": core_evidence["target"],
                "libc": platform.libc_ver(),
                "profiles": results,
                "candidate_sha256": {
                    w.name: digest(w) for w in house.glob("outerspace_apizr*.whl")
                },
                "actual_hash_equals_lock_and_is_admitted": True,
                "outside_checkout": True,
                "preparation_did_not_install_or_activate": True,
                "preparer_and_global_state_unchanged": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--without-mcp", action="store_true")
    parser.add_argument("--expect-glibc")
    args = parser.parse_args()
    prove(args.output.resolve(), sys.executable, args.without_mcp, args.expect_glibc)

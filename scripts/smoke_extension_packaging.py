"""V04-01: real separate installs, outside checkout, with core integrity evidence."""

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def require_uv() -> str:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError(
            "uv is required; install it explicitly. Nothing was downloaded."
        )
    return uv


def run(argv: list[str], cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        argv, cwd=cwd, env=env, text=True, capture_output=True, timeout=300
    )
    if result.returncode:
        raise RuntimeError(f"Command failed: {argv}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def snapshot(root: Path) -> dict[str, str]:
    """Include additions/deletions, file bytes/modes and symlink targets; no exclusions."""
    result = {}
    for path in sorted(root.rglob("*")):
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            value = "link:" + os.readlink(path)
        elif path.is_file():
            value = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            value = "directory"
        result[path.relative_to(root).as_posix()] = f"{mode:o}:{value}"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work-dir", type=Path, required=True, help="New path outside checkout"
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--core-python", type=Path, help="Existing real Homebrew/pipx install"
    )
    parser.add_argument(
        "--core-root", type=Path, help="Entire formula/tool prefix to hash"
    )
    args = parser.parse_args()
    uv = require_uv()  # Must fail before creating directories or invoking anything.
    work = args.work_dir.resolve()
    if work.is_relative_to(REPO) or REPO.is_relative_to(work):
        parser.error("Use a new work directory outside the checkout")
    if bool(args.core_python) != bool(args.core_root):
        parser.error("--core-python and --core-root must be supplied together")
    work.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, UV_PYTHON_DOWNLOADS="never", UV_LINK_MODE="copy")
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["UV_TOOL_DIR"] = str(work / "tools")
    env["UV_TOOL_BIN_DIR"] = str(work / "bin")
    wheels = work / "wheels"
    wheels.mkdir()
    if args.core_python:
        core_python = args.core_python.absolute()
        core_root = args.core_root.resolve()
    else:
        run([uv, "build", "--wheel", str(REPO), "--out-dir", str(wheels)], work, env)
        wheel = next(wheels.glob("outerspace_apizr-*.whl"))
        run([uv, "tool", "install", "--python", args.python, str(wheel)], work, env)
        core_root = work / "tools" / "outerspace-apizr"
        core_python = core_root / "bin" / "python"
    if core_root.is_relative_to(REPO) or not core_python.is_file():
        raise RuntimeError("An installed core outside checkout is required")

    def core(code: str) -> str:
        return run([str(core_python), "-I", "-B", "-c", code], work, env)

    location = Path(core("import apizr; print(apizr.__file__)"))
    if not location.resolve().is_relative_to(core_root) or location.is_relative_to(
        REPO
    ):
        raise RuntimeError("Core import did not come from the recorded installation")
    inventory_code = (
        "import json; from importlib.metadata import distributions; "
        "print(json.dumps(sorted((d.metadata['Name'], d.version) for d in distributions())))"
    )
    before = snapshot(core_root)
    distributions = core(inventory_code)
    run(
        [
            uv,
            "build",
            "--wheel",
            str(REPO / "examples/extension-probe"),
            "--out-dir",
            str(wheels),
        ],
        work,
        env,
    )
    plugin_root = work / "plugins" / "probe-v1"
    plugin_python = plugin_root / "bin" / "python"
    run([uv, "venv", "--python", args.python, str(plugin_root)], work, env)
    run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(plugin_python),
            "--no-deps",
            "--no-index",
            str(next(wheels.glob("apizr_extension_probe-*.whl"))),
        ],
        work,
        env,
    )
    result = json.loads(
        run(
            [
                str(core_python),
                "-I",
                "-B",
                "-m",
                "apizr._prototypes.extension",
                str(plugin_python),
            ],
            work,
            env,
        )
    )
    core(
        "import importlib.util; assert importlib.util.find_spec('apizr_extension_probe') is None"
    )
    plugin_inventory = run(
        [str(plugin_python), "-I", "-B", "-c", inventory_code], work, env
    )
    if json.loads(plugin_inventory) != [["apizr-extension-probe", "0.0.0"]]:
        raise RuntimeError("Unexpected extension environment dependencies")
    # Change only the protocol in otherwise valid messages, so rejection cannot
    # accidentally be explained by missing fields or a mismatched digest.
    digest = result["result"]["source_digest"]
    bad_request = subprocess.run(
        [str(plugin_python), "-I", "-B", "-m", "apizr_extension_probe"],
        input=json.dumps(
            {
                "protocol": "apizr.extension-probe/v999",
                "request_id": "packaging-proof",
                "operation": "describe",
                "source_digest": digest,
            }
        ),
        text=True,
        capture_output=True,
        cwd=work,
        env=env,
        timeout=10,
    )
    if (
        bad_request.returncode != 2
        or "Unsupported extension request" not in bad_request.stderr
    ):
        raise RuntimeError("Extension accepted incompatible protocol")
    bad_response = json.dumps(dict(result, protocol="apizr.extension-probe/v999"))
    core(
        "from apizr._prototypes.extension import Request, validate_response; "
        "from pydantic import ValidationError; "
        f"r=Request(source_digest={digest!r})\n"
        f"try: validate_response({bad_response!r}, r)\n"
        "except ValidationError: pass\n"
        "else: raise AssertionError('Incompatible response accepted')"
    )
    after = snapshot(core_root)
    after_distributions = core(inventory_code)
    evidence = {
        "installer": "external (see installer receipt)"
        if args.core_python
        else "uv tool install",
        "uv": run([uv, "--version"], work, env),
        "core_python": str(core_python),
        "core_module": str(location),
        "core_version": core(
            "from importlib.metadata import version; print(version('outerspace-apizr'))"
        ),
        "python": core("import sys; print(sys.version)"),
        "plugin_python": str(plugin_python),
        "result": result,
        "incompatible_protocol_rejected": True,
        "before": before,
        "after": after,
        "distributions_before": json.loads(distributions),
        "distributions_after": json.loads(after_distributions),
        "plugin_distributions": json.loads(plugin_inventory),
        "core_unchanged": before == after and distributions == after_distributions,
    }
    (work / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if not evidence["core_unchanged"]:
        raise RuntimeError("Core environment changed; inspect evidence.json")
    print(
        f"PASS: separate installed extension; unchanged core; {work / 'evidence.json'}"
    )


if __name__ == "__main__":
    main()

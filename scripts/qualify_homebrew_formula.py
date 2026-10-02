"""Real disposable-tap qualification; no public tap, release or Formula submission."""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from homebrew_formula import BUILD_MANIFEST, ROOT, VERSION, render
from prepare_homebrew_build_inputs import digest, encoded
from smoke_extension_packaging import snapshot

TAP = "apizr-qualification/formula"
FORMULA = TAP + "/apizr"


def qualify(candidate, commit, output, host):
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError(
            "Only the qualified Apple Silicon Homebrew target is supported"
        )
    if (
        host == "physical"
        and subprocess.check_output(
            ["sysctl", "-n", "kern.hv_vmm_present"], text=True
        ).strip()
        != "0"
    ):
        raise ValueError("Physical evidence cannot come from a VM")
    output = output.resolve()
    if output.is_relative_to(ROOT) or output.exists():
        raise ValueError("Use a new proof directory outside the checkout")
    output.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update(
        HOMEBREW_NO_AUTO_UPDATE="1",
        HOMEBREW_NO_INSTALL_CLEANUP="1",
        HOMEBREW_NO_AUTOREMOVE="1",
        HOMEBREW_NO_ANALYTICS="1",
        HOMEBREW_DEVELOPER="1",
        HOMEBREW_FORMULA_BUILD_NETWORK="deny",
        PYTHONDONTWRITEBYTECODE="1",
    )
    results = {}

    def run(name, argv, *, cwd=output, timeout=300):
        proc = subprocess.run(
            list(map(str, argv)),
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        log = proc.stdout + proc.stderr
        for old, new in [
            (str(output), "$PROOF"),
            (str(candidate.resolve()), "$CANDIDATE"),
            (str(ROOT), "$REPOSITORY"),
            (str(Path.home()), "$HOME"),
        ]:
            log = log.replace(old, new)
        (output / (name + ".log")).write_text(log)
        if proc.returncode:
            raise RuntimeError(f"Qualification gate failed: {name}\n{log[-6000:]}")
        results[name] = "success"
        return proc.stdout

    taps = run("tap-inventory", ["brew", "tap"]).splitlines()
    installed = run("formula-inventory", ["brew", "list", "--formula"]).splitlines()
    if TAP in taps or "apizr" in installed:
        raise ValueError(
            "Refusing to alter an existing Apizr install or qualification tap"
        )
    tap = output / "tap"
    receipt = render(candidate, commit, tap, mode="qualification")
    run("git-init", ["git", "init", tap])
    run("git-add", ["git", "-C", tap, "add", "."])
    run(
        "git-commit",
        [
            "git",
            "-C",
            tap,
            "-c",
            "user.name=Apizr qualification",
            "-c",
            "user.email=qualification@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "test: qualify local Apizr Formula",
        ],
    )
    tapped = False
    try:
        run("tap", ["brew", "tap", TAP, tap.as_uri()])
        tapped = True
        run("trust", ["brew", "trust", "--formula", FORMULA])
        run("style", ["brew", "style", FORMULA])
        run("readall", ["brew", "readall", TAP])
        run("install", ["brew", "install", "--build-from-source", FORMULA], timeout=900)
        run("audit", ["brew", "audit", "--strict", FORMULA])
        run("test", ["brew", "test", FORMULA])
        info = json.loads(run("info", ["brew", "info", "--json=v2", FORMULA]))[
            "formulae"
        ][0]
        if info["name"] != "apizr" or not any(
            x["version"] == VERSION for x in info["installed"]
        ):
            raise RuntimeError("Installed Formula version mismatch")
        prefix = Path(run("prefix", ["brew", "--prefix", FORMULA]).strip()).resolve()
        provider = Path(
            run("provider-prefix", ["brew", "--prefix", "pydantic"]).strip()
        ).resolve()
        python = prefix / "libexec/bin/python"
        inventory = json.loads(
            run(
                "imports",
                [
                    python,
                    "-I",
                    "-B",
                    "-c",
                    """
import importlib.metadata as md, importlib.util, json, pathlib, sys
import apizr, pydantic, pydantic_core
core = pathlib.Path(sys.argv[1]); provider = pathlib.Path(sys.argv[2])
assert pathlib.Path(apizr.__file__).resolve().is_relative_to(core / 'libexec')
assert all(pathlib.Path(m.__file__).resolve().is_relative_to(provider) for m in (pydantic, pydantic_core))
assert not importlib.util.find_spec('hatchling') and not importlib.util.find_spec('trove_classifiers')
local = sorted((d.metadata['Name'], d.version) for d in md.distributions(path=[str(core / 'libexec/lib/python3.14/site-packages')]))
assert local == [('outerspace-apizr', '0.4.2')]
parts = tuple(map(int, pydantic.__version__.split('.')[:2]))
assert (2, 12) <= parts < (3, 0)
print(json.dumps({'python': sys.version.split()[0], 'pydantic': pydantic.__version__,
                 'pydantic_core': pydantic_core.__version__, 'apizr': md.version('outerspace-apizr'),
                 'core_import': 'formula-libexec', 'provider_imports': 'homebrew-pydantic',
                 'build_tool_leakage': False}))
""",
                    prefix,
                    provider,
                ],
            )
        )
        if any(p.name == "build-wheelhouse" for p in prefix.rglob("*")):
            raise RuntimeError("Build wheelhouse leaked into the runtime")
        cli = prefix / "bin/apizr"
        if run("version", [cli, "--version"]).strip() != "outerspace-apizr " + VERSION:
            raise RuntimeError("Installed CLI version mismatch")
        project = output / "project"
        project.mkdir()
        (project / "sample.py").write_text(
            "def add(a: int, b: int = 2) -> int:\n    return a + b\n"
        )
        run("init", [cli, "init", project, "--json"])
        doctor = json.loads(
            run(
                "doctor",
                [
                    cli,
                    "doctor",
                    "--project",
                    project / "apizr.toml",
                    "--operator-policy",
                    project / ".apizr/operator.json",
                    "--json",
                ],
            )
        )
        if any(c["status"] == "fail" for c in doctor["checks"]):
            raise RuntimeError("Installed doctor failed")
        for shell in ("bash", "zsh", "fish"):
            if not run("completion-" + shell, [cli, "completion", shell]).strip():
                raise RuntimeError("Empty installed completion")
        run(
            "ci-check",
            [
                cli,
                "ci",
                "check",
                "--project",
                project / "apizr.toml",
                "--output-dir",
                output / "ci-evidence",
                "--authorize-project-analysis",
            ],
        )
        before = snapshot(prefix)
        plugins = output / "plugin-lifecycle"
        run(
            "plugin-lifecycle",
            [
                sys.executable,
                ROOT / "scripts/smoke_extension_packaging.py",
                "--work-dir",
                plugins,
                "--core-python",
                python,
                "--core-root",
                prefix,
            ],
            timeout=900,
        )
        run(
            "plugin-sync-update",
            [sys.executable, ROOT / "scripts/run_plugin_sync_proof.py", plugins],
            timeout=900,
        )
        if snapshot(prefix) != before:
            raise RuntimeError("Formula prefix changed during plugin lifecycle")
        plugin_proof = json.loads((plugins / "evidence.json").read_text())
        if not plugin_proof["core_unchanged"] or plugins.resolve().is_relative_to(
            prefix
        ):
            raise RuntimeError("Plugin separation failed")
        after = digest(encoded(before))
        proof = {
            "schema": "apizr.homebrew-formula/v1",
            **{k: v for k, v in receipt.items() if k != "schema"},
            "homebrew": run("brew-version", ["brew", "--version"]).splitlines()[0],
            "runtime": inventory,
            "platform": {"os": "macos", "architecture": "arm64", "host": host},
            "build_network": "denied by Homebrew sandbox",
            "pep517_isolation": True,
            "pip_no_index": True,
            "pip_config_file": "/dev/null",
            "runtime_dependency_resolution": False,
            "prefix_before_sha256": after,
            "prefix_after_sha256": after,
            "plugins_outside_cellar": True,
            "online_audit": "deferred until public archive exists",
            "intel_macos": "Tier 3; not qualified; non-blocking",
            "linux_homebrew": "not qualified",
            "public_tap": "not published",
        }
    finally:
        if tapped:
            # Only the disposable Formula/tap created by this invocation can be removed.
            current = subprocess.check_output(
                ["brew", "list", "--formula"], env=env, text=True
            ).splitlines()
            if "apizr" in current:
                run("uninstall", ["brew", "uninstall", "--formula", FORMULA])
            run("untrust", ["brew", "untrust", "--formula", FORMULA])
            run("untap", ["brew", "untap", TAP])
    if receipt["build_inputs_manifest_sha256"] != BUILD_MANIFEST:
        raise RuntimeError("Build manifest changed")
    proof["checks"] = {
        k: results[k]
        for k in (
            "style",
            "readall",
            "audit",
            "install",
            "test",
            "info",
            "version",
            "init",
            "doctor",
            "completion-bash",
            "completion-zsh",
            "completion-fish",
            "ci-check",
            "plugin-lifecycle",
            "plugin-sync-update",
            "uninstall",
            "untap",
        )
    }
    # Export only the portable contract and generated tap source, never raw host logs.
    evidence = output / "evidence"
    evidence.mkdir()
    shutil.copytree(tap / "Formula", evidence / "Formula")
    shutil.copy2(tap / "README.md", evidence / "README.md")
    (evidence / "proof.json").write_bytes(encoded(proof))
    print("PASS: real Homebrew Formula, isolated core and unchanged Cellar prefix")
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", choices=["physical", "hosted-vm"], required=True)
    args = parser.parse_args()
    qualify(args.candidate, args.source_sha, args.output, args.host)


if __name__ == "__main__":
    main()

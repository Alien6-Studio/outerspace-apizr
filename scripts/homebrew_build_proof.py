"""Qualify the runtime-provider/build-input split; never install an Apizr Formula."""

import argparse
import json
import os
import platform
import subprocess
import tempfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from prepare_homebrew_build_inputs import digest, encoded, manifest, verify_wheel

ROOT = Path(__file__).resolve().parents[1]


def run(argv, cwd, *, env=None, combined=False):
    result = subprocess.run(
        list(map(str, argv)),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode:
        raise RuntimeError(f"Command failed: {argv}\n{result.stdout}\n{result.stderr}")
    return result.stdout + result.stderr if combined else result.stdout


def candidate_source(candidate, commit):
    evidence = json.loads((candidate / "candidate.json").read_text())
    if (
        evidence["schema"] != "apizr.release-candidate/v1"
        or evidence["repository"] != "Alien6-Studio/outerspace-apizr"
        or evidence["commit"] != commit
        or evidence["version"] not in {"0.4.3", "0.4.4"}
    ):
        raise ValueError("Unexpected coordinated candidate identity")
    filename = f"outerspace_apizr-{evidence['version']}.tar.gz"
    items = [a for a in evidence["artifacts"] if a["file"] == "dist/" + filename]
    if len(items) != 1:
        raise ValueError("Missing exact core sdist")
    source = candidate / items[0]["file"]
    data = source.read_bytes()
    if digest(data) != items[0]["sha256"] or len(data) != items[0]["bytes"]:
        raise ValueError("Coordinated source bytes changed")
    return source, items[0]["sha256"]


def prove(candidate, commit, inputs, output):
    if platform.system() != "Darwin":
        raise RuntimeError(
            "This qualification requires macOS Homebrew and sandbox-exec"
        )
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("Use a fresh proof directory outside the checkout")
    source, source_hash = candidate_source(candidate.resolve(), commit)
    expected = manifest(ROOT / "uv.lock", ROOT / "policy/homebrew-build-inputs.json")
    if json.loads((inputs / "build-inputs.json").read_text()) != expected:
        raise ValueError("Wheelhouse does not match the reviewed build inputs")
    wheelhouse = (inputs / "build-wheelhouse").resolve()
    if {p.name for p in wheelhouse.iterdir()} != {
        d["filename"] for d in expected["distributions"]
    }:
        raise ValueError("Unexpected wheelhouse contents")
    closure = {d["name"]: d["version"] for d in expected["distributions"]}
    for item in expected["distributions"]:
        verify_wheel((wheelhouse / item["filename"]).read_bytes(), item, closure)
    output.mkdir(parents=True, exist_ok=False)
    python_prefix = Path(run(["brew", "--prefix", "python@3.14"], output).strip())
    pydantic_prefix = Path(run(["brew", "--prefix", "pydantic"], output).strip())
    python = python_prefix / "bin/python3.14"
    brew_info = json.loads(
        run(["brew", "info", "--json=v2", "python@3.14", "pydantic"], output)
    )
    formulas = {
        f["name"]: {
            "stable": f["versions"]["stable"],
            "installed": [i["version"] for i in f["installed"]],
        }
        for f in brew_info["formulae"]
    }
    # Upgrades may retain older kegs. The import proof below checks the active
    # provider's exact version and location; unrelated retained kegs are harmless.
    if "2.13.5" not in formulas["pydantic"]["installed"]:
        raise RuntimeError("The first qualification requires Homebrew Pydantic 2.13.5")
    policy = json.loads((ROOT / "policy/homebrew-build-inputs.json").read_text())
    if (
        formulas["pydantic"]["stable"]
        not in Requirement(policy["runtime"]["constraint"]).specifier
    ):
        raise RuntimeError(
            "Current Homebrew Pydantic violates Apizr's runtime constraint"
        )
    guard = ROOT / "scripts/homebrew_network_guard.py"
    sandbox = [
        "/usr/bin/sandbox-exec",
        "-p",
        "(version 1)(allow default)(deny network*)",
    ]
    wheels = output / "wheels"
    wheels.mkdir()
    network_events = []
    with tempfile.TemporaryDirectory(prefix="build-", dir=output) as temporary:
        build = Path(temporary)
        for name in ("tmp", "cache", "config", "instrumentation"):
            (build / name).mkdir()
        # No inherited pip configuration, PYTHONPATH, proxy or index variables.
        env = {
            "PATH": os.environ["PATH"],
            "HOME": str(build / "config"),
            "TMPDIR": str(build / "tmp"),
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_NO_INDEX": "1",
            "PIP_FIND_LINKS": str(wheelhouse),
            "PIP_CACHE_DIR": str(build / "cache"),
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(build / "instrumentation"),
            "APIZR_BUILD_PROOF_ROOT": str(build),
            "APIZR_BUILD_NETWORK_GUARD": str(guard),
        }
        (build / "instrumentation/sitecustomize.py").write_text(
            f"# apizr-build-network-observer\nexec(compile(open({str(guard)!r}).read(), {str(guard)!r}, 'exec'))\n"
        )
        run([python, "-I", "-m", "venv", build / "frontend"], build)
        frontend = build / "frontend/bin/python"
        # Prove both refusal layers before the actual build, then reset observer evidence.
        refusal = run(
            [
                *sandbox,
                frontend,
                "-c",
                "import socket\ntry: socket.create_connection(('127.0.0.1', 9))\nexcept RuntimeError: print('audit-refused')\nelse: raise AssertionError('network guard missing')",
            ],
            build,
            env=env,
        )
        if refusal.strip() != "audit-refused":
            raise RuntimeError("Network observer did not refuse the control")
        (build / "network-events.jsonl").unlink()
        denied = run(
            [
                *sandbox,
                frontend,
                "-I",
                "-c",
                "import socket\ntry: socket.socket().bind(('127.0.0.1', 0))\nexcept PermissionError: print('os-refused')\nelse: raise AssertionError('OS network denial missing')",
            ],
            build,
            env=env,
        )
        if denied.strip() != "os-refused":
            raise RuntimeError("OS network denial did not refuse the control")
        log = run(
            [
                *sandbox,
                frontend,
                ROOT / "scripts/homebrew_pip_build.py",
                "wheel",
                "--no-deps",
                "--no-cache-dir",
                "--verbose",
                "--wheel-dir",
                wheels,
                source,
            ],
            build,
            env=env,
            combined=True,
        )
        dynamic_file = build / "dynamic-requirements.jsonl"
        if not dynamic_file.is_file():
            raise RuntimeError("Dynamic PEP 517 requirements were not observed")
        dynamic = [json.loads(line) for line in dynamic_file.read_text().splitlines()]
        for requirements in dynamic:
            for value in requirements:
                req = Requirement(value)
                version = closure.get(canonicalize_name(req.name))
                if req.url or version is None or version not in req.specifier:
                    raise RuntimeError("Unreviewed dynamic PEP 517 requirement")
        network_events = [
            json.loads(line)
            for line in (build / "network-events.jsonl").read_text().splitlines()
        ]
        if any(e["event"] == "network_attempt" for e in network_events):
            raise RuntimeError("Build tooling attempted network access")
        hooks = {e.get("hook") for e in network_events}
        if not {"get_requires_for_build_wheel", "build_wheel"}.issubset(hooks):
            raise RuntimeError("Backend children escaped network observation")
        # Keep compact logs portable; temporary PEP 517 environments are discarded.
        for path, replacement in (
            (build, "$BUILD"),
            (wheelhouse, "$BUILD_WHEELHOUSE"),
            (source.parent, "$CANDIDATE_DIST"),
            (ROOT, "$REPOSITORY"),
        ):
            log = log.replace(str(path), replacement)
        (output / "offline-build.log").write_text(log)
    (output / "build-phase.json").write_bytes(
        encoded(
            {
                "dynamic_requirements": dynamic,
                "network_events": network_events,
                "source_sha256": source_hash,
                "build_environment_destroyed": not build.exists(),
            }
        )
    )
    if build.exists():
        raise RuntimeError("Temporary build environment survived")
    built = list(wheels.glob("*.whl"))
    if len(built) != 1 or built[0].name != "outerspace_apizr-0.4.4-py3-none-any.whl":
        raise RuntimeError("Unexpected built wheel")
    wheel = built[0]
    with zipfile.ZipFile(wheel) as archive:
        metadata = BytesParser().parsebytes(
            archive.read("outerspace_apizr-0.4.4.dist-info/METADATA")
        )
        runtime_requirements = [
            r for r in metadata.get_all("Requires-Dist", []) if "extra ==" not in r
        ]
        if (
            metadata["Name"] != "outerspace-apizr"
            or metadata["Version"] != "0.4.4"
            or runtime_requirements != ["pydantic<3,>=2.12"]
        ):
            raise RuntimeError("Built runtime metadata changed")
        if any(
            n.startswith(
                ("hatchling/", "tomlkit/", "trove_classifiers/", "build-wheelhouse/")
            )
            for n in archive.namelist()
        ):
            raise RuntimeError("Build tooling embedded in Apizr wheel")
    runtime = output / "runtime"
    run(
        [
            python,
            "-I",
            "-m",
            "venv",
            "--without-pip",
            "--system-site-packages",
            runtime,
        ],
        output,
    )
    # Reproduce the official virtualenv_create dependency path mechanism. This does
    # not alter the global Python environment and works with an unlinked keg too.
    (runtime / "lib/python3.14/site-packages/homebrew_deps.pth").write_text(
        f"import site; site.addsitedir({str(pydantic_prefix / 'lib/python3.14/site-packages')!r})\n"
    )
    runtime_python = runtime / "bin/python"
    runtime_env = {
        "PATH": os.environ["PATH"],
        "PIP_NO_INDEX": "1",
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    run(
        [
            *sandbox,
            python,
            "-I",
            "-m",
            "pip",
            "--python=" + str(runtime_python),
            "install",
            "--no-deps",
            "--no-cache-dir",
            wheel,
        ],
        output,
        env=runtime_env,
    )
    inventory_code = """import json,sys,pathlib,importlib.metadata,importlib.util,apizr,pydantic,pydantic_core
runtime=pathlib.Path(sys.argv[1]).resolve(); provider=pathlib.Path(sys.argv[2]).resolve()
assert pathlib.Path(apizr.__file__).resolve().is_relative_to(runtime)
locations={m.__name__:str(pathlib.Path(m.__file__).resolve().relative_to(provider)) for m in (pydantic,pydantic_core)}
assert pydantic.__version__=='2.13.5' and pydantic_core.__version__=='2.46.5'
assert all(importlib.util.find_spec(name) is None for name in ('hatchling', 'tomlkit', 'trove_classifiers'))
local_distributions=sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions(path=[str(runtime/'lib/python3.14/site-packages')]))
assert local_distributions==[('outerspace-apizr','0.4.4')]
print(json.dumps({'python':sys.version.split()[0],'apizr_module':str(pathlib.Path(apizr.__file__).resolve().relative_to(runtime)),'provider_modules':locations,'pydantic':pydantic.__version__,'pydantic_core':pydantic_core.__version__,'local_distributions':local_distributions,'distributions':sorted(set((d.metadata.get('Name'),d.version) for d in importlib.metadata.distributions()),key=lambda pair:(pair[0] or '',pair[1] or ''))}))
"""
    inventory = json.loads(
        run(
            [
                *sandbox,
                runtime_python,
                "-I",
                "-B",
                "-c",
                inventory_code,
                runtime,
                pydantic_prefix,
            ],
            output,
            env=runtime_env,
        )
    )
    cli = [*sandbox, runtime / "bin/apizr"]
    version = run([*cli, "--version"], output, env=runtime_env).strip()
    if "0.4.4" not in version:
        raise RuntimeError("Installed CLI version mismatch")
    project = output / "project"
    project.mkdir()
    (project / "sample.py").write_text(
        "def add(a: int, b: int = 2) -> int:\n    return a + b\n"
    )
    init = json.loads(run([*cli, "init", project, "--json"], output, env=runtime_env))
    tomllib.loads((project / "apizr.toml").read_text())
    doctor = json.loads(
        run(
            [
                *cli,
                "doctor",
                "--project",
                project / "apizr.toml",
                "--operator-policy",
                project / ".apizr/operator.json",
                "--json",
            ],
            output,
            env=runtime_env,
        )
    )
    if any(check["status"] == "fail" for check in doctor["checks"]):
        raise RuntimeError("Installed local doctor failed")
    if digest(source.read_bytes()) != source_hash:
        raise RuntimeError("Selected sdist changed during proof")
    evidence = {
        "schema": "apizr.homebrew-build-proof/v1",
        "candidate": {"commit": commit, "filename": source.name, "sha256": source_hash},
        "build_inputs_sha256": digest(encoded(expected)),
        "homebrew": run(["brew", "--version"], output).splitlines()[0],
        "architecture": platform.machine(),
        "formulas": formulas,
        "isolation": True,
        "pip_no_index": True,
        "pip_find_links": "build-wheelhouse",
        "empty_initial_cache": True,
        "dynamic_requirements": dynamic,
        "network": {
            "os_denial_control": True,
            "audit_refusal_control": True,
            "events": network_events,
            "attempts": 0,
        },
        "build_environment_destroyed": True,
        "wheel": {
            "filename": wheel.name,
            "sha256": digest(wheel.read_bytes()),
            "runtime_requirements": runtime_requirements,
        },
        "runtime": inventory,
        "runtime_dependency_resolution": False,
        "version": version,
        "init_valid": bool(init),
        "doctor_passed": True,
        "formula_qualification": False,
    }
    (output / "proof.json").write_bytes(encoded(evidence))
    print("PASS: offline isolated build and separate Homebrew-Pydantic runtime")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prove(args.candidate, args.source_sha, args.inputs, args.output)


if __name__ == "__main__":
    main()

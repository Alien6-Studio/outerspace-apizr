"""Prove selected security tests fail when their production protection is removed.

Mutations run only in a disposable copy. A green mutant, collection error,
skipped test, timeout or changed source anchor fails this gate.
"""

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Mutation:
    name: str
    path: str
    before: str
    after: str
    test: str


MUTATIONS = (
    Mutation(
        "analysis-executes-source",
        "src/apizr/capabilities/analyzer.py",
        '    tree = ast.parse(text, filename="<capability-source>")',
        '    exec(text, {})\n    tree = ast.parse(text, filename="<capability-source>")',
        "tests/capabilities/test_properties.py::test_hostile_source_never_executes_any_phase",
    ),
    Mutation(
        "bundle-symlink-escape",
        "src/apizr/governed/runtime.py",
        "    if not target.resolve(strict=True).is_relative_to(root.resolve()):",
        "    if False:",
        "tests/governed/test_artifacts.py::test_startup_refuses_unavailable_host_and_path_escape",
    ),
    Mutation(
        "bundle-artifact-integrity",
        "src/apizr/governed/runtime.py",
        "            if Digest.of_bytes(artifact(self.root, name)) != expected_digest:",
        "            if False:",
        "tests/governed/test_artifacts.py::test_startup_rejects_missing_or_modified_artifacts[execution/worker.py-rest]",
    ),
    Mutation(
        "policy-unsupported-control",
        "src/apizr/execution/policy.py",
        "    if requested - set(backend.enforced):",
        "    if False:",
        "tests/execution/test_policy.py::test_backend_capability_availability_and_required_support",
    ),
    Mutation(
        "output-follows-symlink",
        "src/apizr/interfaces/output.py",
        "os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW",
        "os.O_RDONLY | os.O_DIRECTORY",
        "tests/rest/test_output.py::test_output_symlink_and_symlink_parent_are_rejected",
    ),
    *(
        Mutation(
            "oci-" + flag.removeprefix("--").split("=")[0],
            "src/apizr/oci/docker.py",
            f'            "{flag}",\n'
            + {
                "--pids-limit": "            str(resources.pids),\n",
                "--memory": "            str(resources.memory_bytes),\n",
                "--memory-swap": "            str(resources.memory_bytes),\n",
                "--cpu-quota": "            str(resources.cpu_millis * 100),\n",
            }.get(flag, ""),
            "",
            "tests/oci/test_provider.py::test_create_has_no_escape_hatches_or_environment_values",
        )
        for flag in (
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true",
            "--user=65532:65532",
            "--ipc=private",
            "--cgroupns=private",
            "--pids-limit",
            "--memory",
            "--memory-swap",
            "--cpu-quota",
        )
    ),
)


def run_tests(root: Path, tests: list[str], report: Path, log: Path) -> int:
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(root / "src"), str(root))),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    with log.open("w") as output:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--no-cov",
                "--timeout=60",
                "-o",
                "addopts=",
                "--junitxml=" + str(report),
                *tests,
            ],
            cwd=root,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )
    return result.returncode


def validate_result(report: Path, returncode: int, *, mutated: bool) -> None:
    tree = ET.parse(report)
    cases = tree.findall(".//testcase")
    if not cases or tree.findall(".//error") or tree.findall(".//skipped"):
        raise ValueError("Missing, skipped or errored security test")
    failures = tree.findall(".//failure")
    if not mutated:
        if returncode != 0 or failures:
            raise ValueError("Unmodified security tests must pass")
    elif (
        returncode != 1
        or not failures
        or any(
            not failure.get("message", "").startswith(
                ("AssertionError", "assert ", "Failed: DID NOT RAISE")
            )
            for failure in failures
        )
    ):
        raise ValueError(
            "Mutation must cause an assertion failure in its designated test"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("mutation-evidence"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    results = []
    with tempfile.TemporaryDirectory(prefix="apizr-mutations-") as directory:
        checkout = Path(directory)
        for name in ("src", "tests"):
            shutil.copytree(
                root / name,
                checkout / name,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        shutil.copyfile(root / "pyproject.toml", checkout / "pyproject.toml")
        tests = sorted({mutation.test for mutation in MUTATIONS})
        baseline = output / "baseline.xml"
        validate_result(
            baseline,
            run_tests(checkout, tests, baseline, output / "baseline.log"),
            mutated=False,
        )
        for mutation in MUTATIONS:
            target = checkout / mutation.path
            original = target.read_text()
            if original.count(mutation.before) != 1:
                raise ValueError(f"{mutation.name}: expected exactly one source anchor")
            replacement = original.replace(mutation.before, mutation.after, 1)
            ast.parse(replacement)
            report = output / (mutation.name + ".xml")
            try:
                target.write_text(replacement)
                code = run_tests(
                    checkout, [mutation.test], report, output / (mutation.name + ".log")
                )
                validate_result(report, code, mutated=True)
                results.append(
                    {"name": mutation.name, "test": mutation.test, "result": "killed"}
                )
                print(f"{mutation.name}: killed by {mutation.test}", flush=True)
            finally:
                target.write_text(original)
    (output / "summary.json").write_text(
        json.dumps({"baseline": "passed", "mutations": results}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()

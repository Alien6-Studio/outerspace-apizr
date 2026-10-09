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
        "preparation-admitted-hash",
        "src/apizr/plugins/preparation/selection.py",
        "    if selected.sha256 not in pin.hashes:",
        "    if False:",
        "tests/local_plugins/test_preparation_selection.py::test_best_wheel_with_unadmitted_hash_does_not_fallback_to_weaker_match",
    ),
    Mutation(
        "preparation-retained-bytes",
        "src/apizr/plugins/preparation/selection.py",
        "        if digest not in pin.hashes or digest != selected.sha256:",
        "        if False:",
        "tests/local_plugins/test_preparation_selection.py::test_real_download_checks_retained_bytes_and_admitted_hashes[post_transfer_tamper]",
    ),
    Mutation(
        "preparation-ambiguous-selection",
        "src/apizr/plugins/preparation/selection.py",
        "    if len(compatible) != 1:",
        "    if False:",
        "tests/local_plugins/test_preparation.py::test_refusal_never_publishes_partial_output[ambiguous-wheel_selection_ambiguous]",
    ),
    Mutation(
        "preparation-offline-closure",
        "src/apizr/plugins/preparation/operations.py",
        "                if actual != {",
        "                if False and actual != {",
        "tests/local_plugins/test_preparation_boundaries.py::test_failed_transaction_has_no_partial_publication[closure_changed-resolver_lock_mismatch]",
    ),
    Mutation(
        "mcp-view-repository-identity",
        "plugins/mcp/src/apizr_mcp/worker.py",
        "and digest.value != job.arguments.expected_repository_digest",
        "and False",
        "tests/mcp_plugin/test_views.py::test_every_view_enforces_complete_repository_digest",
    ),
    Mutation(
        "structured-stdlib-authority",
        "src/apizr/readiness/structured.py",
        'or facts.typing_marker(node.bases[0], {"TypedDict"}) != "TypedDict"',
        "or False",
        "tests/structured_contracts/test_static.py::test_authority_failures",
    ),
    Mutation(
        "object-required-fields",
        "src/apizr/interfaces/runtime.py",
        'elif field["required"]:',
        "elif False:",
        "tests/structured_contracts/test_runtime.py::test_required_extra_fields_and_mapping_order",
    ),
    Mutation(
        "object-extra-fields",
        "src/apizr/interfaces/runtime.py",
        'if set(value) - {field["name"] for field in fields}:',
        "if False:",
        "tests/structured_contracts/test_runtime.py::test_required_extra_fields_and_mapping_order",
    ),
    Mutation(
        "selected-scope-required-initialization",
        "src/apizr/exposure/scope.py",
        "            reasons = initialization_reasons(unit)",
        "            reasons = ()",
        "tests/exposure/test_scope.py::test_required_module_initialization_without_any_callable_is_not_guessed",
    ),
    Mutation(
        "repository-unproven-dependency-eligibility",
        "src/apizr/repository_readiness/eligibility.py",
        "                and reason.line in proven",
        "                and True",
        "tests/repository_interfaces/test_local_imports.py::test_external_dependency_is_not_admitted_even_with_complete_graph",
    ),
    Mutation(
        "oci-absence-http-status",
        "plugins/oci/src/apizr_oci/absence.py",
        "            if error.code != 404:",
        "            if False:",
        "tests/oci_plugin/test_absence.py::test_ambiguous_or_failed_observation_never_means_absent[auth]",
    ),
    Mutation(
        "governance-selected-bundle-digest",
        "src/apizr/repository_interfaces/evidence.py",
        "    if Digest.of_bytes(raw) != expected:",
        "    if False:",
        "tests/repository_interfaces/test_evidence.py::test_export_verify_after_removing_business_code[rest]",
    ),
    Mutation(
        "attest-verdict-receipt-binding",
        "plugins/attest/src/apizr_attest/verdict.py",
        '        or report.get("receipt") != "receipt.yaml"\n',
        "",
        "tests/attest_plugin/test_admission.py::test_substitution_never_promotes[receipt]",
    ),
    Mutation(
        "attest-verdict-fields",
        "plugins/attest/src/apizr_attest/verdict.py",
        "        or set(report) != FIELDS\n",
        "",
        "tests/attest_plugin/test_verdict.py::test_unknown_field_refused",
    ),
    Mutation(
        "attest-verdict-check-fields",
        "plugins/attest/src/apizr_attest/verdict.py",
        "            or set(check) != CHECK_FIELDS\n",
        "",
        "tests/attest_plugin/test_verdict.py::test_malformed_check_refused[extra-value]",
    ),
    Mutation(
        "source-analysis-admission",
        "src/apizr/workspace/source_access.py",
        "        decision = decide_analysis(operator_policy, target)",
        "        from apizr.operator_policy import Decision\n        decision = Decision(allowed=True, code='authorized')",
        "tests/source_analysis/test_authorization.py::test_all_public_filesystem_apis_refuse_before_traversal[missing-operator_policy_required-scan]",
    ),
    Mutation(
        "git-operator-admission",
        "src/apizr/git_source/acquisition.py",
        "    if not decision.allowed:",
        "    if False:",
        "tests/git_source/test_operator_policy.py::test_cli_and_api_refuse_before_effect[command0-missing-https]",
    ),
    Mutation(
        "git-exact-source",
        "src/apizr/workspace/operator_policy.py",
        'grants = [g for g in grants if g.target == target]\n    if not grants:\n        return Decision(allowed=False, code="operator_git_source_denied")',
        'grants = [g for g in grants if True]\n    if not grants:\n        return Decision(allowed=False, code="operator_git_source_denied")',
        "tests/git_source/test_operator_policy.py::test_pure_exact_decision[https-prefix]",
    ),
    Mutation(
        "build-operator-admission",
        "src/apizr/plugins/local/activation.py",
        "            if not decision.allowed:",
        "            if False:",
        "tests/local_plugins/test_build_policy.py::test_build_cli_and_api_refuse_before_effect[missing-operator_policy_required-build]",
    ),
    Mutation(
        "build-exact-target",
        "src/apizr/workspace/operator_policy.py",
        "g.target == building",
        "True",
        "tests/local_plugins/test_build_policy.py::test_build_decision_is_pure[prefix-operator_build_denied]",
    ),
    Mutation(
        "signing-operator-admission",
        "src/apizr/plugins/local/activation.py",
        "            if not decision.allowed:",
        "            if False:",
        "tests/local_plugins/test_signing_policy.py::test_signing_cli_and_api_refuse_before_effect[missing-operator_policy_required-attest]",
    ),
    Mutation(
        "signing-timestamp-authority",
        "src/apizr/workspace/operator_policy.py",
        "tsa_identity(g.tsa_url) == authority",
        "True",
        "tests/local_plugins/test_signing_policy.py::test_signing_decision_is_pure[tsa_prefix-operator_tsa_denied]",
    ),
    Mutation(
        "publication-operator-admission",
        "src/apizr/plugins/local/activation.py",
        "            if not decision.allowed:",
        "            if False:",
        "tests/local_plugins/test_operator_policy.py::test_managed_cli_and_api_refuse_before_effect[push]",
    ),
    Mutation(
        "publication-repository-prefix",
        "src/apizr/workspace/operator_policy.py",
        "g.repository == repository",
        "repository.startswith(g.repository)",
        "tests/local_plugins/test_operator_policy.py::test_exact_grants_without_external_io[prefix-operator_repository_denied-push]",
    ),
    Mutation(
        "subprocess-deny-kernel-action",
        "src/apizr/subprocess_guard/filter.py",
        "DENIED = 0x00050000 | errno.EPERM",
        "DENIED = 0x7FFF0000",
        "tests/subprocess_guard/test_contract.py::test_bpf_denies_native_creation_compat_abis_and_x32_aliases",
    ),
    Mutation(
        "subprocess-deny-worker-protocol",
        "src/apizr/subprocess_guard/provider.py",
        "if image.Id != runtime.image or image.Config.Labels.get(LABEL) != PROTOCOL:",
        "if image.Id != runtime.image:",
        "tests/subprocess_guard/test_contract.py::test_provider_requires_independent_protocol_label",
    ),
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
    Mutation(
        "local-process-group-kill",
        "src/apizr/execution/supervisor.py",
        "def kill_group(process: subprocess.Popen[bytes]) -> None:\n    try:",
        "def kill_group(process: subprocess.Popen[bytes]) -> None:\n"
        "    process.kill()\n    process.wait()\n    return\n    try:",
        "tests/execution/test_process.py::test_ordinary_descendant_is_stopped_with_worker",
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
        for name in ("src", "tests", "scripts", "plugins"):
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

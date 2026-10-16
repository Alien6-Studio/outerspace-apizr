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
        "telemetry-context-opt-out",
        "src/apizr/telemetry/consent.py",
        '        and env.get("APIZR_TELEMETRY_ALLOWED", "1") == "1"',
        "        and True",
        "tests/telemetry/test_controls.py::test_preference_byte_boundary_and_disabled_context_does_not_read",
    ),
    Mutation(
        "telemetry-memory-count-bound",
        "src/apizr/telemetry/collection.py",
        "                    or self._total >= 1000",
        "                    or False",
        "tests/telemetry/test_controls.py::test_bounded_memory_and_disable_discard_all_scopes",
    ),
    Mutation(
        "telemetry-disable-discards-counters",
        "src/apizr/telemetry/consent.py",
        "    discard_all()",
        "    pass",
        "tests/telemetry/test_controls.py::test_bounded_memory_and_disable_discard_all_scopes",
    ),
    Mutation(
        "telemetry-report-byte-limit",
        "src/apizr/telemetry/model.py",
        "MAX_REPORT_BYTES = 16384",
        "MAX_REPORT_BYTES = 16385",
        "tests/telemetry/test_contract.py::test_byte_boundary_encoding_and_forged_models",
    ),
    Mutation(
        "telemetry-unknown-report-field",
        "src/apizr/telemetry/model.py",
        'class UsageReport(BaseModel):\n    model_config = ConfigDict(\n        extra="forbid",',
        'class UsageReport(BaseModel):\n    model_config = ConfigDict(\n        extra="ignore",',
        "tests/telemetry/test_contract.py::test_reusable_contract_fixtures[invalid-path]",
    ),
    Mutation(
        "telemetry-loopback-only-override",
        "src/apizr/telemetry/preview.py",
        "            or not ipaddress.ip_address(parsed.hostname).is_loopback",
        "            or False",
        "tests/telemetry/test_contract.py::test_external_or_unsafe_override_refused[http://192.0.2.1:1234]",
    ),
    Mutation(
        "transport-http-cumulative-bytes",
        "src/apizr/interfaces/http_admission.py",
        "            if len(body) + len(chunk) > self.max_bytes:",
        "            if False:",
        "tests/interfaces/test_http_admission.py::test_chunked_byte_limit_rejects_before_decoder[headers0]",
    ),
    Mutation(
        "transport-http-predecode-structure",
        "src/apizr/interfaces/http_admission.py",
        "                preflight(bytes(body), max_bytes=self.max_bytes)",
        "                pass",
        "tests/interfaces/test_http_admission.py::test_structure_and_encoding_refused_before_decoder[depth]",
    ),
    Mutation(
        "transport-graph-wide-before-copy",
        "src/apizr/interfaces/json_budget.py",
        "            if count * (2 if isinstance(value, dict) else 1) > self.remaining_nodes:",
        "            if False:",
        "tests/interfaces/test_json_budget.py::test_broad_containers_refused_without_iteration[False]",
    ),
    Mutation(
        "transport-graph-depth",
        "src/apizr/interfaces/json_budget.py",
        "            if depth >= self.max_depth:",
        "            if False:",
        "tests/interfaces/test_json_budget.py::test_depth_boundary_matches_raw_admission_and_precedes_decoder",
    ),
    Mutation(
        "transport-graph-encoded-bytes",
        "src/apizr/interfaces/json_budget.py",
        "        if self.remaining_bytes < 0:",
        "        if False:",
        "tests/interfaces/test_json_budget.py::test_exact_compact_utf8_budget[None]",
    ),
    Mutation(
        "transport-string-escape-cost",
        "src/apizr/interfaces/json_budget.py",
        '            self.charge(len(piece[1:-1].encode("utf-8")))',
        '            self.charge(len(value[offset : offset + 4096].encode("utf-8")))',
        "tests/interfaces/test_json_budget.py::test_string_escape_amplification_is_counted_in_small_chunks",
    ),
    Mutation(
        "transport-stdio-bounded-binary-read",
        "src/apizr/generators/mcp/transport.py",
        "        raw = self.stream.readline(self.max_bytes + 1)",
        "        raw = self.stream.readline()",
        "tests/mcp_generator/test_admission.py::test_production_line_read_is_bounded_without_allocating_large_input",
    ),
    Mutation(
        "transport-stdio-predecode-structure",
        "src/apizr/generators/mcp/transport.py",
        "            return preflight(raw, max_bytes=self.max_bytes)",
        '            return raw.decode("utf-8")',
        "tests/mcp_generator/test_admission.py::test_structural_refusal_is_small_and_next_frame_survives[depth]",
    ),
    Mutation(
        "transport-stdio-byte-refusal",
        "src/apizr/generators/mcp/transport.py",
        "        if len(raw) > self.max_bytes:",
        "        if False:",
        "tests/mcp_generator/test_admission.py::test_binary_byte_limit_precedes_decoding_and_ends_oversized_stream",
    ),
    Mutation(
        "transport-mcp-result-representations",
        "src/apizr/generators/mcp/transport.py",
        "    JsonBudget(max_bytes=MAX_JSON_BYTES - 1024).visit(",
        "    JsonBudget().visit(",
        "tests/mcp_generator/test_admission.py::test_mcp_dual_representation_is_admitted_before_sdk_models",
    ),
    Mutation(
        "transport-rest-predecode-middleware",
        "src/apizr/generators/rest/runtime.py",
        "    app.add_middleware(JsonAdmission)",
        "    pass",
        "tests/interfaces/test_transport_admission.py::test_all_transports_refuse_structure_before_decoder_and_recover[rest-single-direct]",
    ),
    Mutation(
        "transport-mcp-predecode-middleware",
        "src/apizr/generators/mcp/transport.py",
        "        app.add_middleware(JsonAdmission, max_bytes=limit)",
        "        pass",
        "tests/interfaces/test_transport_admission.py::test_all_transports_refuse_structure_before_decoder_and_recover[mcp-single-direct]",
    ),
    Mutation(
        "transport-oci-complete-closure",
        "plugins/oci/src/apizr_oci/snapshot.py",
        "        allowed |= TRANSPORT_MODULES | ADMISSION_MODULES",
        "        allowed |= TRANSPORT_MODULES.intersection(manifest.artifacts) | ADMISSION_MODULES",
        "tests/oci_plugin/test_build.py::test_transport_admission_closure_is_complete_and_verified[partial-rest-apizr_http_admission.py]",
    ),
    Mutation(
        "oci-bundle-admission-complete-closure",
        "plugins/oci/src/apizr_oci/snapshot.py",
        "        allowed |= ADMISSION_MODULES",
        "        allowed |= ADMISSION_MODULES.intersection(manifest.artifacts)",
        "tests/oci_plugin/test_build.py::test_portable_admission_closure_is_copied_verified_and_closed[legacy-partial-reader-rest]",
    ),
    Mutation(
        "bundle-bounded-read",
        "src/apizr/repository_interfaces/artifacts.py",
        "            content = stream.read(limit + 1)",
        "            content = stream.read()",
        "tests/repository_interfaces/test_artifact_bounds.py::test_file_growth_still_uses_a_bounded_read",
    ),
    Mutation(
        "bundle-stat-admission",
        "src/apizr/repository_interfaces/artifacts.py",
        "            if metadata.st_size > limit:",
        "            if False:",
        "tests/repository_interfaces/test_artifact_bounds.py::test_sparse_oversized_file_is_refused_without_reading",
    ),
    Mutation(
        "bundle-remaining-aggregate",
        "src/apizr/repository_interfaces/artifacts.py",
        "        return min(artifact_limit(name), MAX_BUNDLE_BYTES - self.size)",
        "        return artifact_limit(name)",
        "tests/repository_interfaces/test_artifact_bounds.py::test_total_allowance_includes_manifest_and_precedes_next_read",
    ),
    Mutation(
        "bundle-count-before-read",
        "src/apizr/repository_interfaces/artifacts.py",
        "        if len(names) + self.count > MAX_BUNDLE_ARTIFACTS:",
        "        if False:",
        "tests/repository_interfaces/test_artifact_bounds.py::test_count_checked_before_opening_any_member",
    ),
    Mutation(
        "bundle-json-before-decoding",
        "src/apizr/repository_interfaces/artifacts.py",
        '    if name.endswith(".json") and not name.startswith("source/"):',
        "    if False:",
        "tests/repository_interfaces/test_artifact_bounds.py::test_manifest_structure_refused_before_any_decoder[nodes-direct]",
    ),
    Mutation(
        "bundle-direct-aggregate",
        "src/apizr/repository_interfaces/runtime.py",
        '    artifacts = budget.read_many(root, manifest["artifacts"])',
        '    artifacts = {name: read_artifact(root, name) for name in manifest["artifacts"]}',
        "tests/repository_interfaces/test_artifact_bounds.py::test_all_runtime_contracts_charge_the_whole_retained_set[bytes-direct]",
    ),
    Mutation(
        "bundle-governed-aggregate",
        "src/apizr/governed_repository/runtime.py",
        "        artifacts = budget.read_many(self.root, manifest.artifacts)",
        "        artifacts = {name: read_artifact(self.root, name) for name in manifest.artifacts}",
        "tests/repository_interfaces/test_artifact_bounds.py::test_all_runtime_contracts_charge_the_whole_retained_set[bytes-governed]",
    ),
    Mutation(
        "bundle-worker-aggregate",
        "src/apizr/repository_execution/worker.py",
        "        sources = budget.read_many(",
        "        sources = BundleBudget().read_many(",
        "tests/repository_interfaces/test_artifact_bounds.py::test_all_runtime_contracts_charge_the_whole_retained_set[bytes-worker]",
    ),
    Mutation(
        "bundle-source-reread-limit",
        "src/apizr/repository_interfaces/runtime.py",
        'read_artifact(self.root, source["bundle_path"], source["size"])',
        'read_artifact(self.root, source["bundle_path"])',
        "tests/repository_interfaces/test_artifact_bounds.py::test_changed_source_size_is_bounded_again_before_compile",
    ),
    Mutation(
        "bundle-generation-admission",
        "src/apizr/repository_interfaces/generator.py",
        "    check_bundle(artifacts)\n",
        "",
        "tests/repository_interfaces/test_artifact_bounds.py::test_renderer_refuses_unloadable_bundle[False]",
    ),
    Mutation(
        "bundle-governed-generation-admission",
        "src/apizr/governed_repository/embedding.py",
        "    check_bundle(artifacts)\n",
        "",
        "tests/repository_interfaces/test_artifact_bounds.py::test_renderer_refuses_unloadable_bundle[True]",
    ),
    Mutation(
        "notebook-admitted-snapshot-export",
        "src/apizr/notebooks/exporter.py",
        "                source, resources = self.exporter.from_file(\n                    content, resources=resources\n                )",
        "                source, resources = self.exporter.from_filename(\n                    filename, resources=resources\n                )",
        "tests/capabilities/test_source_bounds.py::test_notebook_export_uses_admitted_snapshot_after_file_changes",
    ),
    Mutation(
        "wheel-zip64-directory-selection",
        "src/apizr/plugins/artifacts/central_directory.py",
        '                and data[location : location + 4] == b"PK\\x06\\x06"',
        "                and False",
        "tests/local_plugins/test_central_directory_bounds.py::test_zip64_extensible_record_cannot_hide_a_second_directory",
    ),
    Mutation(
        "wheel-central-directory-before-index",
        "src/apizr/plugins/artifacts/wheel.py",
        "    preflight_directory(data)\n",
        "",
        "tests/local_plugins/test_central_directory_bounds.py::test_entry_budget_precedes_zipfile_even_with_forged_counts[0]",
    ),
    Mutation(
        "source-regular-read-budget",
        "src/apizr/capabilities/source.py",
        'MAX_SOURCE_BYTES if selected.suffix == ".py" else MAX_NOTEBOOK_BYTES',
        "MAX_SOURCE_BYTES * 2",
        "tests/capabilities/test_source_bounds.py::test_large_regular_source_is_bounded_before_parsing[read_source]",
    ),
    Mutation(
        "source-encoded-byte-budget",
        "src/apizr/capabilities/analyzer.py",
        "    if len(raw) > MAX_SOURCE_BYTES:",
        "    if False:",
        "tests/capabilities/test_source_bounds.py::test_inmemory_source_limit_precedes_parser[unicode]",
    ),
    Mutation(
        "source-analysis-structure-budget",
        "src/apizr/capabilities/analyzer.py",
        "    check_tree(tree)\n",
        "",
        "tests/capabilities/test_source_bounds.py::test_broad_and_deep_asts_are_refused_before_recursive_analysis[nodes]",
    ),
    Mutation(
        "notebook-json-before-materialization",
        "src/apizr/contracts/json_budget.py",
        "        if nodes > max_nodes or depth > max_depth:",
        "        if False:",
        "tests/capabilities/test_source_bounds.py::test_notebook_budget_precedes_json_decoder[nodes-code_cells]",
    ),
    Mutation(
        "notebook-export-before-materialization",
        "src/apizr/notebooks/exporter.py",
        "            raw = notebook_text(content.read(MAX_NOTEBOOK_BYTES + 1))",
        '            raw = content.read(MAX_NOTEBOOK_BYTES + 1).decode("utf-8")',
        "tests/capabilities/test_source_bounds.py::test_notebook_budget_precedes_json_decoder[depth-exporter]",
    ),
    Mutation(
        "signing-verification-authority",
        "src/apizr/workspace/operator_policy.py",
        "signing_grants = [g for g in signing_grants if g.verification == target]",
        "signing_grants = signing_grants",
        "tests/local_plugins/test_verification_policy.py::test_verification_authority_is_exact_and_pure[tool_hash-attest]",
    ),
    Mutation(
        "publication-verification-authority",
        "src/apizr/workspace/operator_policy.py",
        "if isinstance(g, Grant) and g.verification == target",
        "if isinstance(g, Grant)",
        "tests/local_plugins/test_verification_policy.py::test_verification_authority_is_exact_and_pure[signer-publish]",
    ),
    Mutation(
        "admission-verification-authority",
        "src/apizr/workspace/operator_policy.py",
        "if isinstance(g, Grant) and g.verification == target",
        "if isinstance(g, Grant)",
        "tests/local_plugins/test_verification_policy.py::test_verification_authority_is_exact_and_pure[trust_path-admit]",
    ),
    Mutation(
        "attest-trust-snapshot-identity",
        "plugins/attest/src/apizr_attest/delivery.py",
        "if expected_sha256 is not None and trust_identity(files) != expected_sha256:",
        "if False:",
        "tests/attest_plugin/test_delivery.py::test_changed_trust_refused_before_verifier_or_key_access",
    ),
    Mutation(
        "builtin-provider-identity",
        "src/apizr/scientific_providers/builtin/provider.py",
        "        if request.provider.identity != self.descriptor.identity:",
        "        if False:",
        "tests/scientific_providers/test_builtin.py::test_reference_provider_rejects_other_identity_and_aggregate_limits",
    ),
    Mutation(
        "builtin-provider-admission",
        "src/apizr/scientific_providers/builtin/provider.py",
        "        return admit_result(result, request=request)",
        "        return result",
        "tests/scientific_providers/test_builtin.py::test_reference_provider_rejects_other_identity_and_aggregate_limits",
    ),
    Mutation(
        "scientific-provider-python-line-boundary",
        "src/apizr/experiments/source_analysis.py",
        '.split("\\n")',
        ".splitlines()",
        "tests/scientific_providers/test_contracts.py::test_python_line_positions_ignore_unicode_separators",
    ),
    Mutation(
        "scientific-provider-source-facts-binding",
        "src/apizr/experiments/provider_source.py",
        "type(analysis) is SourceAnalysis and analysis.source == result.text",
        "type(analysis) is SourceAnalysis",
        "tests/scientific_providers/test_analysis.py::test_revalidation_reuses_only_matching_immutable_facts",
    ),
    Mutation(
        "scientific-provider-retained-identity",
        "src/apizr/scientific_providers/contracts/selection.py",
        "and self.descriptor.identity != self.choice.identity",
        "and False",
        "tests/scientific_providers/test_selection.py::test_retained_provider_identity_cannot_change",
    ),
    Mutation(
        "scientific-provider-selection-readmission",
        "src/apizr/scientific_providers/selection/operations.py",
        "admitted = admit_result(candidate, request=request)",
        "admitted = candidate",
        "tests/scientific_providers/test_selection.py::test_refusal_is_unknown_no_exception_or_fallback[invalid-True-provider_result_invalid]",
    ),
    Mutation(
        "scientific-provider-source-digest",
        "src/apizr/scientific_providers/contracts/admission.py",
        "            or result.source_digest != request.source.digest\n",
        "",
        "tests/scientific_providers/test_contracts.py::test_identity_source_schema_and_unknown_fields_are_rejected[source_digest]",
    ),
    Mutation(
        "sdk-malformed-metric-refused",
        "src/apizr/tracking/session.py",
        "item = capture_metric(name, value, unit=unit)",
        "item = capture_metric(name, 0.0, unit=unit)",
        "tests/tracking/test_sessions.py::test_invalid_metric_and_non_string_name_are_sanitized",
    ),
    Mutation(
        "sdk-aggregate-payload-bound",
        "src/apizr/tracking/session.py",
        "if self._bytes + size > MAX_CAPTURE_BYTES:",
        "if False:",
        "tests/tracking/test_sessions.py::test_counts_and_aggregate_bytes_are_bounded",
    ),
    Mutation(
        "sdk-concurrent-task-authority",
        "src/apizr/tracking/session.py",
        "and expected[1] is observed[1]",
        "and True",
        "tests/tracking/test_sessions.py::test_async_tasks_do_not_write_to_inherited_parent_context",
    ),
    Mutation(
        "sdk-finalization-releases-context",
        "src/apizr/tracking/session.py",
        "                _ACTIVE.reset(self._token)",
        "                pass",
        "tests/tracking/test_sessions.py::test_interrupted_publication_leaves_no_partial_run_and_releases_context[keyboard]",
    ),
    Mutation(
        "sdk-corrupt-record-digest",
        "src/apizr/experiments/store.py",
        "if expected_run != run_digest(run) or expected_plan != plan_digest(plan):",
        "if False:",
        "tests/tracking/test_history.py::test_corrupted_sdk_record_never_bypasses_validation",
    ),
    Mutation(
        "scientific-provider-failure-stays-unknown",
        "src/apizr/scientific_providers/selection/operations.py",
        '                except Exception:\n                    code = "provider_failed"',
        "                except Exception:\n                    code = None",
        "tests/scientific_providers/test_selection.py::test_refusal_is_unknown_no_exception_or_fallback[raise-True-provider_failed]",
    ),
    Mutation(
        "scientific-provider-static-input",
        "src/apizr/scientific_providers/contracts/model.py",
        "                or item.digest is not None\n",
        "",
        "tests/scientific_providers/test_contracts.py::test_static_provider_cannot_assert_input_content_observations[digest]",
    ),
    Mutation(
        "scientific-adapter-finite-value",
        "src/apizr/tracking/adapters.py",
        "        log_metric(name, value, unit=unit)\n",
        "        log_metric(name, 0.0, unit=unit)\n",
        "tests/tracking/test_adapters.py::test_adapter_never_bypasses_experiment_value_validation[nonfinite]",
    ),
    Mutation(
        "preparation-qualified-uv-series",
        "src/apizr/plugins/preparation/resolver.py",
        "or (int(match[2]), int(match[3])) not in QUALIFIED_UV_SERIES",
        "or False",
        "tests/local_plugins/test_preparation_resolver_versions.py::test_only_qualified_stable_series_are_measured",
    ),
    Mutation(
        "preparation-glibc-native-host",
        "src/apizr/plugins/preparation/target.py",
        'if sys.platform != "linux" or target.machine != host_platform.machine():',
        "if False:",
        "tests/local_plugins/test_preparation_target.py::test_glibc_241_native_resolution_refuses_a_foreign_host",
    ),
    Mutation(
        "preparation-glibc-native-resolution",
        "src/apizr/plugins/preparation/resolver.py",
        "elif not resolver.target.native_resolution:",
        "else:",
        "tests/local_plugins/test_preparation_resolver_versions.py::test_native_glibc_resolution_never_substitutes_an_older_platform",
    ),
    Mutation(
        "single-worker-restores-capture-context",
        "src/apizr/execution/worker.py",
        'os.environ.pop("APIZR_SERVED_PROCESS", None)',
        "pass",
        "tests/execution/test_serving_context.py::test_worker_restores_callers_serving_marker",
    ),
    Mutation(
        "repository-worker-restores-capture-context",
        "src/apizr/repository_execution/worker.py",
        'os.environ.pop("APIZR_SERVED_PROCESS", None)',
        "pass",
        "tests/execution/test_serving_context.py::test_worker_restores_callers_serving_marker",
    ),
    Mutation(
        "sdk-binding-is-not-name-matching",
        "src/apizr/capabilities/instrumentation.py",
        'if self.member(target) != "experiment":',
        "if False:",
        "tests/readiness/test_tracking_decorators.py::test_unproven_or_stacked_decorator_remains_unknown",
    ),
    Mutation(
        "sdk-import-binding-must-be-unique",
        "src/apizr/capabilities/instrumentation.py",
        "if len(events) != 1:",
        "if False:",
        "tests/readiness/test_tracking_decorators.py::test_unproven_or_stacked_decorator_remains_unknown",
    ),
    Mutation(
        "sdk-local-lookalike-is-not-official",
        "src/apizr/repository_readiness/eligibility.py",
        'if sdk_import and any(name.resolution != "external" for name in declaration.names):',
        "if False:",
        "tests/readiness/test_tracking_decorators.py::test_repository_local_sdk_lookalike_cannot_discharge_dependency",
    ),
    Mutation(
        "sdk-serving-disables-capture",
        "src/apizr/tracking/session.py",
        'or os.environ.get("APIZR_SERVED_PROCESS") == "1"',
        "or False",
        "tests/tracking/test_served.py::test_served_decorator_never_constructs_a_session",
    ),
    Mutation(
        "sdk-service-marker-precedes-project-import",
        "src/apizr/repository_interfaces/generator.py",
        "APIZR_SERVED_PROCESS",
        "APIZR_UNRECOGNIZED_SERVING_MODE",
        "tests/experiments/test_capture_exposure.py::test_instrumented_service_suppresses_capture_before_source_import",
    ),
    Mutation(
        "sdk-exposure-retains-capture-binding",
        "src/apizr/experiments/exposure_model.py",
        'raise ExperimentExposureRefused("experiment_capture_binding_mismatch")',
        "pass",
        "tests/experiments/test_capture_exposure.py::test_portable_binding_cannot_swap_capture_or_observed_source",
    ),
    Mutation(
        "tracking-preserve-business-exception",
        "src/apizr/tracking/session.py",
        "        return False",
        "        return True",
        "tests/tracking/test_sessions.py::test_business_exception_identity_is_preserved",
    ),
    Mutation(
        "tracking-kernel-source-byte-bound",
        "src/apizr/tracking/kernel.py",
        "if len(raw) > MAX_CELL_BYTES:",
        "if False:",
        "tests/tracking/test_kernel.py::test_invalid_observations_refuse_before_business_code_or_store",
    ),
    Mutation(
        "tracking-kernel-execute-request-only",
        "src/apizr/tracking/kernel.py",
        'if cast(dict[str, object], header).get("msg_type") != "execute_request":',
        "if False:",
        "tests/tracking/test_kernel.py::test_non_execution_request_is_not_presented_as_a_cell[completion]",
    ),
    Mutation(
        "development-license-cannot-reach-runtime",
        "scripts/qualification/ci/check_dependency_licenses.py",
        'if exception.get("development_only") and name in runtime:',
        "if False:",
        "tests/test_dependency_licenses.py::test_development_license_exception_cannot_enter_runtime",
    ),
    Mutation(
        "experiment-history-requires-explicit-read-authority",
        "src/apizr/workspace/editor_session.py",
        "    if not decision.allowed:\n        raise AuthorizationDenied(decision.code)",
        "    if False:\n        raise AuthorizationDenied(decision.code)",
        "tests/test_editor_contract.py::test_history_requires_its_own_exact_grant_before_store_io",
    ),
    Mutation(
        "tracking-duplicate-key-refusal",
        "src/apizr/tracking/session.py",
        "        if name in items:",
        "        if False:",
        "tests/tracking/test_sessions.py::test_duplicate_names_are_refused_before_repeated_file_reads",
    ),
    Mutation(
        "tracking-aggregate-byte-refusal",
        "src/apizr/tracking/session.py",
        "if self._bytes + size > MAX_CAPTURE_BYTES:",
        "if False:",
        "tests/tracking/test_collection_cost.py::test_capture_boundary_accepts_exact_bytes_and_refuses_next_item",
    ),
    Mutation(
        "experiment-value-byte-accounting",
        "src/apizr/experiments/values.py",
        "if remaining_bytes < 0:",
        "if False:",
        "tests/experiments/test_value_budget.py::test_exact_value_boundary_and_one_byte_over",
    ),
    Mutation(
        "tracking-cross-context-refusal",
        "src/apizr/tracking/session.py",
        '        if not _same_owner(self._context_owner, _owner()):\n            raise TrackingError("tracking_context_mismatch")\n        if self._closed:',
        "        if self._closed:",
        "tests/tracking/test_sessions.py::test_independent_thread_contexts_and_cross_thread_refusal",
    ),
    Mutation(
        "experiment-v2-capture-binding",
        "src/apizr/experiments/serialization.py",
        '            raise ValueError("experiment_capture_mismatch")',
        "            pass",
        "tests/experiments/test_capture_contract.py::test_binding_refuses_changed_capture_or_subject",
    ),
    Mutation(
        "application-import-exact-provider",
        "src/apizr/repository_readiness/eligibility.py",
        "if declaration.relative_level or module not in external_modules:",
        "if declaration.relative_level:",
        "tests/test_application_dependencies.py::test_wheels_do_not_hide_required_dependency_defects",
    ),
    Mutation(
        "application-wheel-snapshot-binding",
        "src/apizr/repository_interfaces/planner.py",
        "if inspect_application_wheel(filename, raw) != declared[filename]:",
        "if False:",
        "tests/test_application_dependencies.py::test_render_revalidates_provider_evidence_from_exact_retained_wheels",
    ),
    Mutation(
        "readiness-main-module-context",
        "src/apizr/readiness/source.py",
        'module != "__main__"',
        "True",
        "tests/readiness/test_main_guard.py::test_main_module_context_is_not_an_import",
    ),
    Mutation(
        "readiness-main-guard-shadowing",
        "src/apizr/readiness/source.py",
        'and "__name__" not in self.bindings',
        "and True",
        "tests/readiness/test_main_guard.py::test_shadowed_or_mutated_namespace_never_proves_main_guard",
    ),
    Mutation(
        "readiness-main-guard-else",
        "src/apizr/readiness/source.py",
        "and not node.orelse",
        "and True",
        "tests/readiness/test_main_guard.py::test_only_exact_supported_guard_is_recognized",
    ),
    Mutation(
        "readiness-main-guard-indirect-write",
        "src/apizr/readiness/source.py",
        "and not self.indirect_writes",
        "and True",
        "tests/readiness/test_main_guard.py::test_shadowed_or_mutated_namespace_never_proves_main_guard",
    ),
    Mutation(
        "experiment-exposure-success-required",
        "src/apizr/experiments/exposure.py",
        'if record.run.status != "success":',
        "if False:",
        "tests/experiments/test_exposure.py::test_unsuccessful_run_refused_before_io",
    ),
    Mutation(
        "experiment-exposure-explicit-output-selection",
        "src/apizr/experiments/exposure.py",
        "outputs = _outputs(record, artifacts)",
        "outputs = record.run.outputs",
        "tests/experiments/test_exposure.py::test_existing_pipeline_binding_and_selection",
    ),
    Mutation(
        "experiment-exposure-source-admission",
        "src/apizr/experiments/exposure.py",
        "or subject.digest != current.digest.value",
        "or False",
        "tests/experiments/test_exposure_security.py::test_changed_source_refuses_before_repository_planning",
    ),
    Mutation(
        "experiment-exposure-source-membership",
        "src/apizr/experiments/exposure.py",
        "if capability not in {\n        candidate.id for candidate in inspection.serving.capabilities\n    }:",
        "if False:",
        "tests/experiments/test_exposure_security.py::test_unrelated_capability_refuses_before_repository_planning",
    ),
    Mutation(
        "experiment-exposure-observed-dependency-version",
        "src/apizr/experiments/exposure_model.py",
        'pins.append(name + "==" + package.version)',
        'pins.append(name + "==9.9.9")',
        "tests/experiments/test_exposure.py::test_existing_pipeline_binding_and_selection",
    ),
    Mutation(
        "experiment-exposure-run-identity",
        "src/apizr/experiments/exposure_model.py",
        "binding.run_digest != record.run_digest",
        "False",
        "tests/experiments/test_exposure_security.py::test_pure_cross_binding_verifier_rejects_swaps",
    ),
    Mutation(
        "experiment-exposure-plan-identity",
        "src/apizr/experiments/exposure_model.py",
        "binding.plan_digest != record.plan_digest",
        "False",
        "tests/experiments/test_exposure_security.py::test_pure_cross_binding_verifier_rejects_swaps",
    ),
    Mutation(
        "experiment-exposure-artifact-binding",
        "src/apizr/experiments/exposure_model.py",
        "resource.digest.value != output.digest",
        "False",
        "tests/experiments/test_exposure_security.py::test_binding_presence_and_independent_application_checks",
    ),
    Mutation(
        "experiment-exposure-export-preserves-attachment",
        "src/apizr/repository_interfaces/evidence.py",
        'if Path(name).name == name and name.endswith(".json")',
        "if name in DOCUMENTS",
        "tests/experiments/test_exposure.py::test_existing_pipeline_binding_and_selection",
    ),
    Mutation(
        "diff-unknown-is-not-same",
        "src/apizr/experiments/comparison.py",
        "if EvidenceOrigin.UNKNOWN in (a.origin, b.origin):\n        return ChangeState.UNKNOWN",
        "if EvidenceOrigin.UNKNOWN in (a.origin, b.origin):\n        return ChangeState.SAME",
        "tests/experiments/test_comparison.py::test_parameter_unknown_and_membership",
    ),
    Mutation(
        "diff-membership-direction",
        "src/apizr/experiments/comparison.py",
        "return ChangeState.UNKNOWN if b is None else ChangeState.ADDED",
        "return ChangeState.UNKNOWN if b is None else ChangeState.REMOVED",
        "tests/experiments/test_comparison.py::test_remote_reference_and_selection_membership",
    ),
    Mutation(
        "diff-delta-direction",
        "src/apizr/experiments/comparison.py",
        "difference = y - x",
        "difference = x - y",
        "tests/experiments/test_comparison.py::test_metric_rules",
    ),
    Mutation(
        "diff-delta-unit-binding",
        "src/apizr/experiments/comparison.py",
        "a is not None and b is not None and a.unit == b.unit",
        "a is not None and b is not None",
        "tests/experiments/test_comparison.py::test_metric_rules",
    ),
    Mutation(
        "diff-intent-is-not-observation",
        "src/apizr/experiments/comparison.py",
        "content_state=_content(oa, ob)",
        "content_state=_content(pa, pb)",
        "tests/experiments/test_comparison.py::test_dataset_only_change_and_missing_observation",
    ),
    Mutation(
        "diff-record-binding",
        "src/apizr/experiments/comparison.py",
        "a = validate_record(a)",
        "a = a  # mutation: skip caller-provided record validation",
        "tests/experiments/test_comparison.py::test_revalidates_records_and_nested_binding",
    ),
    Mutation(
        "experiment-worker-source-recheck",
        "src/apizr/experiments/worker.py",
        "if sha256(current).hexdigest() != request.subject.digest:",
        "if False:",
        "tests/experiments/test_worker_protocol.py::test_worker_rechecks_source_before_exec[False]",
    ),
    Mutation(
        "experiment-static-randomness-promoted",
        "src/apizr/experiments/runner.py",
        "randomness=(),",
        'randomness=tuple(r.model_copy(update={"origin": EvidenceOrigin.RUNTIME}) for r in plan.randomness),',
        "tests/experiments/test_runner_process.py::test_real_process_bindings_environment_data_outputs_and_history",
    ),
    Mutation(
        "experiment-stale-failed-output",
        "src/apizr/experiments/runner.py",
        'if outcome.status == "success" and not diagnostics:',
        "if True:",
        "tests/experiments/test_runner_process.py::test_status_sanitized_and_failed_outputs_never_captured",
    ),
    Mutation(
        "experiment-store-binding-bypass",
        "src/apizr/experiments/store.py",
        "check_run_binding(run, plan, run.plan_digest)",
        "pass  # mutation: accept a canonical Run bound to a different source",
        "tests/experiments/test_store_history.py::test_corruption_not_hidden_by_filters_or_limits[wrong_binding]",
    ),
    Mutation(
        "experiment-store-publication-binding-bypass",
        "src/apizr/experiments/store.py",
        "validate_run_binding(run, plan)",
        "pass  # mutation: accept a Run bound to a different source",
        "tests/experiments/test_store_history.py::test_wrong_binding_cannot_publish_anything",
    ),
    Mutation(
        "experiment-store-plan-canonical-bypass",
        "src/apizr/experiments/store.py",
        'if (\n                            encode(plan.model_dump(mode="json"), MAX_ARTIFACT_BYTES)\n                            != raw\n                        ):',
        "if False:",
        "tests/experiments/test_store_history.py::test_noncanonical_plan_refused",
    ),
    Mutation(
        "experiment-store-run-canonical-bypass",
        "src/apizr/experiments/store.py",
        'if encode(run.model_dump(mode="json"), MAX_ARTIFACT_BYTES) != raw:',
        "if False:",
        "tests/experiments/test_store_history.py::test_corruption_not_hidden_by_filters_or_limits[noncanonical]",
    ),
    Mutation(
        "experiment-store-digest-bypass",
        "src/apizr/experiments/store.py",
        'if sha256(data).hexdigest() + ".json" != name:',
        "if False:",
        "tests/experiments/test_store_history.py::test_orphan_plan_digest_refused",
    ),
    Mutation(
        "experiment-store-overwrite",
        "src/apizr/experiments/store.py",
        'if _read(directory, name) != payload:\n                raise StoreError("store_corrupt") from None',
        "if _read(directory, name) != payload:\n                os.unlink(name, dir_fd=directory)\n                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)",
        "tests/experiments/test_store_history.py::test_exclusive_publication_failures_leave_original_and_no_stage[conflict]",
    ),
    Mutation(
        "experiment-unrequested-retry",
        "src/apizr/experiments/runner.py",
        "run = execute_plan(inspection, plan, root=root, options=options)",
        "execute_plan(inspection, plan, root=root, options=options)\n    run = execute_plan(inspection, plan, root=root, options=options)",
        "tests/experiments/test_runner_process.py::test_status_sanitized_and_failed_outputs_never_captured",
    ),
    Mutation(
        "experiment-timeout-group-survives",
        "src/apizr/experiments/runner.py",
        "try:\n            kill_group(process)\n        finally:",
        "try:\n            pass  # mutation: leave the live group running\n        finally:",
        "tests/experiments/test_runner_cleanup.py::test_synchronized_descendant_group_cleanup[timeout]",
    ),
    Mutation(
        "inspection-static-metric-captured",
        "src/apizr/experiments/inspection_model.py",
        "metrics=SectionState.PARTIAL",
        "metrics=SectionState.CAPTURED",
        "tests/experiments/test_inspection.py::test_realistic_python_composes_existing_evidence",
    ),
    Mutation(
        "inspection-dynamic-data-captured",
        "src/apizr/experiments/inspection_model.py",
        "if records and not diagnostics and complete",
        "if records and complete",
        "tests/experiments/test_inspection.py::test_explicit_inputs_and_bounded_reads",
    ),
    Mutation(
        "inspection-unseeded-captured",
        "src/apizr/experiments/inspection_model.py",
        "random_state = SectionState.UNCONTROLLED",
        "random_state = SectionState.CAPTURED",
        "tests/experiments/test_inspection.py::test_realistic_python_composes_existing_evidence",
    ),
    Mutation(
        "inspection-source-execution",
        "src/apizr/experiments/inspection.py",
        "    notebook = None\n    source: str | bytes = raw",
        "    exec(raw, {})\n    notebook = None\n    source: str | bytes = raw",
        "tests/experiments/test_inspection_security.py::test_hostile_python_is_parsed_without_execution",
    ),
    Mutation(
        "inspection-fabricated-capability",
        "src/apizr/experiments/inspection.py",
        "id=c.id,",
        'id=f"experiment:{c.id}",',
        "tests/experiments/test_inspection.py::test_canonical_identity_is_preserved_for_valid_source",
    ),
    Mutation(
        "experiment-static-metric-runtime",
        "src/apizr/scientific_providers/builtin/metrics.py",
        "    return MetricDiscoveryResult(\n        signals=tuple(discovery.signals),",
        '    from apizr.experiments.metrics import capture_metric\n    return MetricDiscoveryResult.model_construct(\n        signals=(capture_metric("invented", 0.91),),',
        "tests/experiments/test_metrics.py::test_six_callables_and_safe_aliases",
    ),
    Mutation(
        "experiment-metric-validation",
        "src/apizr/experiments/metrics.py",
        "        return Metric.model_validate(",
        "        return Metric.model_construct(",
        "tests/experiments/test_metrics.py::test_rejected_values_are_not_stringified",
    ),
    Mutation(
        "experiment-output-no-follow",
        "src/apizr/experiments/_files.py",
        "os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK",
        "os.O_RDONLY | os.O_NONBLOCK",
        "tests/experiments/test_outputs_fingerprint.py::test_symlink_swap_after_admission_never_reads",
    ),
    Mutation(
        "experiment-output-mutation",
        "src/apizr/experiments/_files.py",
        '            raise FileFailure("changed_during_read")',
        "            pass",
        "tests/experiments/test_outputs_fingerprint.py::test_changed_during_read_discards_digest",
    ),
    Mutation(
        "experiment-output-deserialization",
        "src/apizr/experiments/outputs.py",
        "        digest, size = fingerprint_file(",
        '        __import__("pickle").loads((root / selection.reference).read_bytes())\n        digest, size = fingerprint_file(',
        "tests/experiments/test_results_security.py::test_output_bytes_are_not_deserialized_or_uploaded",
    ),
    Mutation(
        "experiment-randomness-shadowing",
        "src/apizr/experiments/_lexical.py",
        "            if name not in collector.writes",
        "            if True",
        "tests/experiments/test_randomness.py::test_untrusted_bindings_do_not_grant_framework_authority",
    ),
    Mutation(
        "experiment-randomness-dynamic",
        "src/apizr/scientific_providers/builtin/randomness.py",
        '        return None, "dynamic_randomness_control"',
        "        return 42, None",
        "tests/experiments/test_randomness.py::test_unknown_values",
    ),
    Mutation(
        "experiment-accelerator-uncertainty",
        "src/apizr/scientific_providers/builtin/randomness.py",
        '        if provider in {"torch", "tensorflow"}:',
        "        if False:",
        "tests/experiments/test_randomness.py::test_fixed_literals",
    ),
    Mutation(
        "experiment-environment-content",
        "src/apizr/experiments/environment.py",
        "        result = fingerprint_input(root, selection, policy=policy)",
        '        result = fingerprint_input(root, selection, policy=policy).model_copy(update={"artifacts": (selection.model_copy(update={"content_origin": EvidenceOrigin.UNKNOWN}),)})',
        "tests/experiments/test_environment.py::test_spec_exact_identity",
    ),
    Mutation(
        "experiment-input-mutation",
        "src/apizr/experiments/_files.py",
        '            raise FileFailure("changed_during_read")',
        "            pass",
        "tests/experiments/test_inputs_fingerprint.py::test_changed_during_read_discards_digest[st_mtime_ns]",
    ),
    Mutation(
        "experiment-input-no-follow",
        "src/apizr/experiments/_files.py",
        "os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK",
        "os.O_RDONLY | os.O_NONBLOCK",
        "tests/experiments/test_inputs_security.py::test_symlink_swap_after_admission_is_never_read",
    ),
    Mutation(
        "experiment-plan-binding",
        "src/apizr/experiments/serialization.py",
        "    if run.plan_digest != digest:",
        "    if False:",
        "tests/experiments/test_identity.py::test_binding_rejects_wrong_plan_digest",
    ),
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
    root = Path(__file__).resolve().parents[3]
    results = []
    with tempfile.TemporaryDirectory(prefix="apizr-mutations-") as directory:
        checkout = Path(directory)
        for name in ("src", "tests", "scripts", "plugins", "policy", "architecture"):
            shutil.copytree(
                root / name,
                checkout / name,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        shutil.copyfile(root / "pyproject.toml", checkout / "pyproject.toml")
        shutil.copyfile(root / "uv.lock", checkout / "uv.lock")
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

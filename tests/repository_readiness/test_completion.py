"""Additive v1 execution vocabulary and immutable legacy serialization evidence."""

import hashlib
import itertools
from pathlib import Path
from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from apizr.graph import Graph
from apizr.repository import Catalog
from apizr.repository_readiness import (
    Control,
    ExecutionRequirements,
    RepositoryReadinessPolicy,
    RepositoryReadinessReport,
    assess_repository,
    execution_compatibility,
    policy_bytes,
    report_bytes,
    validate_report,
)
from apizr.repository_readiness.execution import OCI_RESOURCE_FIELDS
from apizr.repository_readiness.reporting import text_report

from .test_readiness import artifacts

FIXTURES = Path(__file__).parents[1] / "fixtures/repository_readiness"
ALL_MODES = ("direct", "local-process", "oci-container")
LOCAL = {
    "wall_timeout",
    "input_limit",
    "output_limit",
    "environment",
    "working_directory",
}
RESOURCES = {"memory_limit", "cpu_limit", "pid_limit"}
OCI = LOCAL | RESOURCES | {"network_deny", "filesystem_sandbox"}


def test_immutable_baseline_policy_and_report_bytes():
    fixture = FIXTURES / "v1"
    c = Catalog.model_validate_json((fixture / "catalog.json").read_bytes())
    g = Graph.model_validate_json((fixture / "graph.json").read_bytes())
    for prefix, policy_sha, report_sha in [
        (
            "legacy-default-",
            "738f8e05129e0c776889f727192ae9d12a8e36832971e57d30ebef7a2b9f4222",
            "81de6b4c9c42372fc6f6110d1dcf9cca3e7c3462c715a6829b0d64359c2dee69",
        ),
        (
            "",
            "fe1771f35bea529e999fceedb3a77dbf8d94f6bdc03382316652748406f2f67a",
            "0801540c24ebf27217bb188ca3d8af540901aa1e09c5a137688ab443b962c64b",
        ),
    ]:
        old_policy = (fixture / f"{prefix}policy.json").read_bytes()
        old_report = (fixture / f"{prefix}report.json").read_bytes()
        assert hashlib.sha256(old_policy).hexdigest() == policy_sha
        assert hashlib.sha256(old_report).hexdigest() == report_sha
        policy = RepositoryReadinessPolicy.model_validate_json(old_policy)
        report = RepositoryReadinessReport.model_validate_json(old_report)
        assert policy_bytes(policy) == old_policy
        assert report_bytes(assess_repository(c, g, policy=policy)) == old_report
        assert report_bytes(validate_report(report, c, g)) == old_report
    assert RepositoryReadinessPolicy().execution.modes == (
        "local-process",
        "oci-container",
    )


def test_all_old_control_subsets_retain_original_compatibility_bytes():
    # Exhaustive legacy input domain: 256 control subsets × 3 nonempty mode subsets.
    from apizr.repository.serialization import canonical_bytes
    from apizr.repository_readiness.execution import ModeCompatibility

    old_controls = sorted(
        LOCAL | {"network_deny", "filesystem_sandbox", "subprocess_deny"}
    )
    for bits in itertools.product([False, True], repeat=len(old_controls)):
        required = tuple(
            c for c, include in zip(old_controls, bits, strict=True) if include
        )
        for modes in [
            ("local-process",),
            ("oci-container",),
            ("local-process", "oci-container"),
        ]:
            results = execution_compatibility(
                ExecutionRequirements(modes=modes, require_controls=required)
            )
            for actual in results:
                supported = LOCAL if actual.mode == "local-process" else OCI - RESOURCES
                missing = sorted(set(required) - supported)
                expected = {
                    "mode": actual.mode,
                    "backend_version": f"apizr.{actual.mode}/v1",
                    "supported_controls": sorted(supported),
                    "missing_controls": missing,
                    "compatible": not missing,
                    "runtime_availability": "not_assessed",
                }
                assert canonical_bytes(actual) == canonical_bytes(
                    ModeCompatibility.model_validate(expected)
                )


@pytest.mark.parametrize(
    "controls",
    [
        (),
        ("wall_timeout",),
        ("memory_limit",),
        ("cpu_limit",),
        ("pid_limit",),
        ("subprocess_deny",),
    ],
)
def test_direct_only_semantics(controls):
    policy = RepositoryReadinessPolicy(
        execution=ExecutionRequirements(modes=("direct",), require_controls=controls)
    )
    c, g = artifacts()
    report = assess_repository(c, g, policy=policy)
    (mode,) = report.execution
    assert mode.supported_controls == ()
    assert mode.missing_controls == tuple(sorted(controls))
    assert mode.compatible is (not controls)
    assert mode.backend_version == "direct"
    assert report.assessments[0].state == ("unsupported" if controls else "ready")


@pytest.mark.parametrize(
    "controls",
    [
        (),
        *[(c,) for c in get_args(Control)],
        ("memory_limit", "cpu_limit", "pid_limit"),
        ("network_deny", "memory_limit"),
        ("network_deny", "memory_limit", "filesystem_sandbox", "pid_limit"),
        tuple(get_args(Control)),
    ],
)
def test_control_conformance_corpus(controls):
    results = execution_compatibility(
        ExecutionRequirements(modes=ALL_MODES, require_controls=controls)
    )
    for mode, supported in zip(results, [set(), LOCAL, OCI], strict=True):
        assert set(mode.supported_controls) == supported
        assert set(mode.missing_controls) == set(controls) - supported
        assert mode.compatible is (set(controls) <= supported)
        assert mode.runtime_availability == "not_assessed"


@given(
    st.sets(st.sampled_from(get_args(Control))),
    st.lists(st.sampled_from(ALL_MODES), min_size=1, max_size=8),
)
def test_mode_and_control_set_normalization_and_no_combined_guarantees(controls, modes):
    requirements = ExecutionRequirements(
        modes=tuple(modes), require_controls=tuple(controls)
    )
    reversed_requirements = ExecutionRequirements(
        modes=tuple(reversed(modes)),
        require_controls=tuple(sorted(controls, reverse=True)),
    )
    assert requirements == reversed_requirements
    result = execution_compatibility(requirements)
    assert result == execution_compatibility(reversed_requirements)
    for mode in result:
        supported = {"direct": set(), "local-process": LOCAL, "oci-container": OCI}[
            mode.mode
        ]
        assert mode.compatible is (controls <= supported)
    p = RepositoryReadinessPolicy(execution=requirements)
    assert policy_bytes(p) == policy_bytes(
        RepositoryReadinessPolicy(execution=reversed_requirements)
    )


def test_static_adapter_tracks_existing_backend_contracts_without_changing_them():
    from apizr.execution.policy import BackendCapabilities
    from apizr.execution.policy import Control as RuntimeControl
    from apizr.oci.model import Resources

    assert set(BackendCapabilities(available=False).enforced) == LOCAL
    assert not RESOURCES & set(get_args(RuntimeControl))
    resources = Resources()
    assert set(OCI_RESOURCE_FIELDS) == RESOURCES
    for field in OCI_RESOURCE_FIELDS.values():
        assert field in Resources.model_fields
        assert getattr(resources, field) > 0
    # Versioned backend models remain the source of configuration facts; the
    # existing provider/integration suites verify actual resource enforcement.
    assert OCI_RESOURCE_FIELDS == {
        "memory_limit": "memory_bytes",
        "cpu_limit": "cpu_millis",
        "pid_limit": "pids",
    }


def test_no_host_or_daemon_availability_probes(monkeypatch):
    import apizr.execution.policy as execution
    import apizr.oci.docker as docker

    def forbidden(*args, **kwargs):
        raise AssertionError("runtime probe")

    monkeypatch.setattr(execution, "local_capabilities", forbidden)
    monkeypatch.setattr(docker.DockerProvider, "probe", forbidden)
    for host in ("invalid://one", "invalid://two"):
        monkeypatch.setenv("DOCKER_HOST", host)
        result = execution_compatibility(
            ExecutionRequirements(modes=ALL_MODES, require_controls=tuple(RESOURCES))
        )
        assert [m.compatible for m in result] == [False, False, True]
        assert all(m.runtime_availability == "not_assessed" for m in result)


def test_new_examples_and_reports_match_additive_schema():
    root = Path(__file__).parents[2]
    c, g = artifacts()
    for name in ("ungoverned", "governed-local", "isolated-oci", "impossible"):
        policy = RepositoryReadinessPolicy.model_validate_json(
            (root / f"examples/readiness/{name}.json").read_bytes()
        )
        report = assess_repository(c, g, policy=policy)
        assert (
            report_bytes(report)
            == (FIXTURES / f"completion/{name}-report.json").read_bytes()
        )
        for model, value in [
            (RepositoryReadinessPolicy, policy),
            (RepositoryReadinessReport, report),
        ]:
            Draft202012Validator(model.model_json_schema()).validate(
                value.model_dump(mode="json")
            )
        text = text_report(report)
        assert (
            "Execution contract compatibility" in text
            and "not a recommendation" in text
        )
        assert (
            "direct:" in text
            and "Recommended backend:" not in text
            and "Best backend:" not in text
        )
        if name == "impossible":
            assert all(not m.compatible for m in report.execution)
            assert report.assessments[0].state == "unsupported"


@pytest.mark.parametrize(
    "controls",
    [
        ("memory_limit",),
        ("cpu_limit",),
        ("pid_limit",),
        ("memory_limit", "cpu_limit", "pid_limit"),
    ],
)
def test_resource_opt_in_with_unchanged_default_modes(controls):
    requirements = ExecutionRequirements(require_controls=controls)
    assert requirements.modes == ("local-process", "oci-container")
    local, oci = execution_compatibility(requirements)
    assert not local.compatible and local.missing_controls == tuple(sorted(controls))
    assert oci.compatible and set(oci.supported_controls) == OCI
    assert not oci.missing_controls
    c, g = artifacts()
    report = assess_repository(
        c, g, policy=RepositoryReadinessPolicy(execution=requirements)
    )
    assert report.assessments[0].state == "ready"

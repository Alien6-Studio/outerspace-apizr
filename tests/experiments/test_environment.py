"""Selected runtime facts and exact bounded specification bytes, never a host dump."""

import importlib.metadata
from hashlib import sha256
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from apizr.experiments import (
    EnvironmentDiagnostic,
    EnvironmentEvidence,
    EnvironmentResult,
    FingerprintPolicy,
    _files,
    capture_runtime_environment,
    discover_environment_specs,
    environment,
)
from apizr.experiments import EvidenceOrigin as O


@pytest.fixture
def facts(monkeypatch):
    monkeypatch.setattr(
        environment,
        "sys",
        SimpleNamespace(
            implementation=SimpleNamespace(name="cpython"),
            version_info=SimpleNamespace(
                major=3, minor=14, micro=8, releaselevel="final", serial=0
            ),
            platform="darwin",
        ),
    )
    monkeypatch.setattr(environment.platform, "machine", lambda: "arm64")
    seen = []

    def version(name):
        seen.append(name)
        versions = {
            "outerspace-apizr": "0.4.4",
            "numpy": "2.4.1",
            "scikit-learn": "1.8.0",
        }
        if name not in versions:
            raise importlib.metadata.PackageNotFoundError(name)
        return versions[name]

    monkeypatch.setattr(importlib.metadata, "version", version)
    return seen


def test_real_facts_from_controlled_observations(facts):
    result = capture_runtime_environment(distributions=("Scikit_Learn", "NumPy"))
    evidence = result.evidence
    assert evidence.python_implementation.value == "cpython"
    assert evidence.python_version.value == "3.14.8"
    assert evidence.platform.value == "darwin"
    assert evidence.architecture.value == "arm64"
    assert all(origin is O.RUNTIME for origin in evidence.origins())
    assert [(p.name, p.version) for p in evidence.packages] == [
        ("numpy", "2.4.1"),
        ("outerspace-apizr", "0.4.4"),
        ("scikit-learn", "1.8.0"),
    ]
    assert facts == ["numpy", "outerspace-apizr", "scikit-learn"]
    assert result.diagnostics == ()


def test_apizr_always_selected_once(facts):
    assert [p.name for p in capture_runtime_environment().evidence.packages] == [
        "outerspace-apizr"
    ]
    facts.clear()
    capture_runtime_environment(distributions=("outerspace_apizr",))
    assert facts == ["outerspace-apizr"]


def test_missing_selected_distribution(facts):
    result = capture_runtime_environment(distributions=("torch",))
    package = result.evidence.packages[1]
    assert (package.name, package.version, package.origin) == ("torch", None, O.UNKNOWN)
    assert result.diagnostics == (
        EnvironmentDiagnostic(code="environment_package_missing", name="torch"),
    )


@pytest.mark.parametrize("value", ["", "x" * 129, "secret\nvalue", "\ud800"])
def test_bad_metadata_redacted(monkeypatch, facts, value):
    monkeypatch.setattr(importlib.metadata, "version", lambda name: value)
    result = capture_runtime_environment()
    assert result.evidence.packages[0].version is None
    assert result.diagnostics[0].code == "environment_package_unreadable"
    assert "secret" not in result.model_dump_json()


def test_unreadable_metadata(monkeypatch, facts):
    def fail(name):
        raise OSError("private host path")

    monkeypatch.setattr(importlib.metadata, "version", fail)
    result = capture_runtime_environment()
    assert result.evidence.packages[0].origin is O.UNKNOWN
    assert "private" not in result.model_dump_json()


@pytest.mark.parametrize(
    "distributions",
    [
        ("numpy", "NumPy"),
        ("bad/name",),
        ("",),
        ("x" * 129,),
        tuple("pkg" + str(i) for i in range(65)),
        ["numpy"],
        (42,),
    ],
)
def test_selection_strict_before_observation(distributions, facts):
    with pytest.raises(ValueError, match="^environment_selection_invalid$"):
        capture_runtime_environment(distributions=distributions)
    assert facts == []


def test_bad_policy_before_observation(facts):
    policy = FingerprintPolicy().model_copy(update={"max_file_bytes": True})
    with pytest.raises(ValueError, match="^environment_selection_invalid$"):
        capture_runtime_environment(policy=policy)
    assert not facts


@pytest.mark.parametrize(
    "level,suffix", [("alpha", "a2"), ("beta", "b2"), ("candidate", "rc2")]
)
def test_prerelease_version(monkeypatch, facts, level, suffix):
    monkeypatch.setattr(
        environment.sys,
        "version_info",
        SimpleNamespace(major=3, minor=15, micro=0, releaselevel=level, serial=2),
    )
    assert (
        capture_runtime_environment().evidence.python_version.value == "3.15.0" + suffix
    )


@pytest.mark.parametrize("machine", ["x86_64", "aarch64", "arm64", ""])
def test_observed_architecture_not_inferred(monkeypatch, facts, machine):
    monkeypatch.setattr(environment.platform, "machine", lambda: machine)
    result = capture_runtime_environment()
    assert result.evidence.architecture.value == (machine or None)
    assert result.evidence.architecture.origin is (O.RUNTIME if machine else O.UNKNOWN)


def test_unavailable_architecture(monkeypatch, facts):
    def fail():
        raise OSError("private")

    monkeypatch.setattr(environment.platform, "machine", fail)
    result = capture_runtime_environment()
    assert result.evidence.architecture.value is None
    assert result.diagnostics[0] == EnvironmentDiagnostic(
        code="environment_value_unavailable", name="architecture"
    )


@pytest.mark.parametrize(
    "name",
    [
        "uv.lock",
        "poetry.lock",
        "requirements.txt",
        "requirements-dev.txt",
        "requirements.lock",
        "requirements-ci.lock",
        "environment.yml",
        "environment.yaml",
        "conda.yml",
        "conda.yaml",
    ],
)
def test_spec_exact_identity(tmp_path, name, facts):
    content = b"not parsed: token-or-package-identity\x00\xff\r\n"
    (tmp_path / name).write_bytes(content)
    static = discover_environment_specs(tmp_path)
    runtime = capture_runtime_environment(root=tmp_path)
    for result, origin in ((static, O.STATIC), (runtime, O.RUNTIME)):
        (artifact,) = result.evidence.artifacts
        assert artifact.name == artifact.reference == name
        assert artifact.digest == sha256(content).hexdigest()
        assert artifact.size == len(content)
        assert artifact.origin is artifact.content_origin is origin
        assert artifact.format_hint is None
        assert not result.diagnostics
        assert str(tmp_path) not in result.model_dump_json()
        assert "token-or-package" not in result.model_dump_json()


def test_root_only_stable_order(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/uv.lock").write_text("nested")
    for name in (
        "uv.lock",
        "requirements-z.txt",
        "poetry.lock",
        "README.md",
        ".env",
        "pyproject.toml",
        "UV.LOCK",
    ):
        (tmp_path / name).write_text(name)
    result = discover_environment_specs(tmp_path)
    assert [a.reference for a in result.evidence.artifacts] == [
        "poetry.lock",
        "requirements-z.txt",
        "uv.lock",
    ]


@pytest.mark.parametrize("runtime", [False, True])
def test_symlink_refused(tmp_path, facts, runtime):
    (tmp_path / "outside").write_text("private target")
    (tmp_path / "uv.lock").symlink_to(tmp_path / "outside")
    result = (
        capture_runtime_environment(root=tmp_path)
        if runtime
        else discover_environment_specs(tmp_path)
    )
    artifact = result.evidence.artifacts[0]
    assert artifact.origin is (O.RUNTIME if runtime else O.STATIC)
    assert artifact.digest is artifact.size is None
    assert artifact.content_origin is O.UNKNOWN
    assert result.diagnostics[0].code == "input_symlink"


def test_root_symlink_and_missing_root_redacted(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    for root in (tmp_path / "link", tmp_path / "missing"):
        result = discover_environment_specs(root)
        assert not result.evidence.artifacts
        assert result.diagnostics[0].code == "environment_specs_unreadable"
        assert str(tmp_path) not in result.model_dump_json()


def test_mutated_spec_discards_digest(tmp_path, monkeypatch, facts):
    (tmp_path / "uv.lock").write_bytes(b"initial")
    original = _files.os.read

    def changed(fd, count):
        chunk = original(fd, count)
        if chunk:
            (tmp_path / "uv.lock").write_bytes(b"changed contents")
        return chunk

    monkeypatch.setattr(_files.os, "read", changed)
    for result in (
        discover_environment_specs(tmp_path),
        capture_runtime_environment(root=tmp_path),
    ):
        assert result.evidence.artifacts[0].digest is None
        assert result.diagnostics[0].code == "input_changed_during_read"


def test_spec_size_policy_and_directory(tmp_path):
    (tmp_path / "uv.lock").write_bytes(b"1234")
    result = discover_environment_specs(
        tmp_path, policy=FingerprintPolicy(max_file_bytes=3)
    )
    assert result.diagnostics[0].code == "input_too_large"
    (tmp_path / "uv.lock").unlink()
    (tmp_path / "uv.lock").mkdir()
    assert (
        discover_environment_specs(tmp_path).diagnostics[0].code == "input_not_regular"
    )


def test_excess_specs_refuse_entire_selection_before_read(tmp_path, monkeypatch):
    for i in range(33):
        (tmp_path / f"requirements-{i}.txt").touch()

    def fail(*args, **kwargs):
        raise AssertionError("must not hash partial selection")

    monkeypatch.setattr(environment, "fingerprint_input", fail)
    result = discover_environment_specs(tmp_path)
    assert not result.evidence.artifacts
    assert result.diagnostics[0].code == "environment_specs_limit"


def test_excess_directory_entries_bounded(tmp_path, monkeypatch):
    for name in ("a", "b", "uv.lock"):
        (tmp_path / name).touch()
    monkeypatch.setattr(environment, "_MAX_ENTRIES", 2)
    result = discover_environment_specs(tmp_path)
    assert not result.evidence.artifacts
    assert result.diagnostics[0].code == "environment_specs_limit"


@pytest.mark.parametrize(
    "name", ["requirements:private.txt", "requirements" + "x" * 120 + ".txt"]
)
def test_invalid_spec_reference_redacted(tmp_path, name):
    (tmp_path / name).touch()
    result = discover_environment_specs(tmp_path)
    assert not result.evidence.artifacts
    assert result.diagnostics[0].code == "environment_spec_reference_invalid"
    assert name not in result.model_dump_json()


def test_environment_result_strict_ordering():
    a = EnvironmentDiagnostic(code="input_symlink", name="uv.lock")
    b = EnvironmentDiagnostic(code="environment_specs_limit")
    assert EnvironmentResult(
        evidence=EnvironmentEvidence(), diagnostics=(a, b, a)
    ).diagnostics == (b, a)
    with pytest.raises(ValidationError):
        EnvironmentResult(evidence=EnvironmentEvidence(), diagnostics=(a,) * 129)

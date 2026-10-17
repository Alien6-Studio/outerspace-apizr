"""Reject allocation amplification before reads, JSON decoding or project imports."""

import importlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from governed_repository.helpers import bundle as governed_bundle
from repository_execution.helpers import planned
from repository_execution.test_local import stage

from apizr.execution.serialization import digest as model_digest
from apizr.governed_repository.runtime import GovernedRuntime
from apizr.interfaces.runtime import IntegrityError
from apizr.repository_execution.model import Request
from apizr.repository_execution.worker import handle
from apizr.repository_interfaces import artifacts as admission
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_interfaces.runtime import RepositoryLoader, digest, load_bundle


def test_sparse_oversized_file_is_refused_without_reading(tmp_path, monkeypatch):
    with (tmp_path / "large").open("wb") as stream:
        stream.truncate(admission.MAX_ARTIFACT_BYTES + 1)

    checks = []
    original = admission.check_artifact

    def observed(*args):
        checks.append(args[0])
        return original(*args)

    monkeypatch.setattr(admission, "check_artifact", observed)
    with pytest.raises(IntegrityError, match="byte limit"):
        admission.read_artifact(tmp_path, "large", admission.MAX_ARTIFACT_BYTES * 2)
    assert checks == []


def test_file_growth_still_uses_a_bounded_read(tmp_path, monkeypatch):
    (tmp_path / "growing").write_bytes(b"123456789")
    original_fdopen = os.fdopen
    original_fstat = os.fstat
    reads = []

    class Stream:
        def __init__(self, *args):
            self.stream = original_fdopen(*args)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def read(self, size=-1):
            reads.append(size)
            assert 0 <= size <= 9, "Read must reserve only the remaining allowance"
            return self.stream.read(size)

    def old_size(descriptor):
        return SimpleNamespace(st_mode=original_fstat(descriptor).st_mode, st_size=0)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "fdopen", Stream)
        scoped.setattr(os, "fstat", old_size)
        with pytest.raises(IntegrityError, match="byte limit"):
            admission.read_artifact(tmp_path, "growing", 8)
    assert reads == [9]


def test_zero_and_negative_allowances_and_artifact_ceiling(tmp_path, monkeypatch):
    (tmp_path / "empty").write_bytes(b"")
    assert admission.read_artifact(tmp_path, "empty", 0) == b""
    with pytest.raises(IntegrityError, match="byte limit"):
        admission.read_artifact(tmp_path, "empty", -1)
    monkeypatch.setattr(admission, "MAX_ARTIFACT_BYTES", 3)
    (tmp_path / "small").write_bytes(b"1234")
    with pytest.raises(IntegrityError, match="byte limit"):
        admission.read_artifact(tmp_path, "small", 100)


@pytest.mark.parametrize(
    "name", ["apizr-repository-rest.json", "apizr-repository-mcp.json"]
)
def test_manifest_has_its_own_byte_ceiling(tmp_path, monkeypatch, name):
    monkeypatch.setattr(admission, "MAX_MANIFEST_BYTES", 8)
    (tmp_path / name).write_bytes(b" " * 9)
    with pytest.raises(IntegrityError, match="byte limit"):
        admission.read_artifact(tmp_path, name)


def test_total_allowance_includes_manifest_and_precedes_next_read(
    tmp_path, monkeypatch
):
    values = {"apizr-repository-rest.json": b"{}  ", "one": b"1234", "two": b"5678"}
    for name, content in values.items():
        (tmp_path / name).write_bytes(content)
    monkeypatch.setattr(admission, "MAX_BUNDLE_BYTES", 10)
    original = admission.read_artifact
    allowances = []

    def observed(root, name, limit=None):
        allowances.append((name, limit))
        return original(root, name, limit)

    monkeypatch.setattr(admission, "read_artifact", observed)
    budget = admission.BundleBudget()
    assert budget.read(tmp_path, "apizr-repository-rest.json") == b"{}  "
    with pytest.raises(IntegrityError, match="byte limit"):
        budget.read_many(tmp_path, ["one", "two"])
    assert allowances == [("apizr-repository-rest.json", 10), ("one", 6), ("two", 2)]
    assert budget.size == 8 and budget.count == 2


def test_count_checked_before_opening_any_member(tmp_path, monkeypatch):
    monkeypatch.setattr(admission, "MAX_BUNDLE_ARTIFACTS", 2)
    budget = admission.BundleBudget()
    for name in ("first", "second", "third"):
        (tmp_path / name).write_bytes(b"1")
    reads = []
    original = admission.read_artifact

    def observed(*args):
        reads.append(args)
        return original(*args)

    monkeypatch.setattr(admission, "read_artifact", observed)
    with pytest.raises(IntegrityError, match="count limit"):
        budget.read_many(tmp_path, ["first", "second", "third"])
    assert reads == []
    (tmp_path / "one").write_bytes(b"1")
    budget.read(tmp_path, "one")
    budget.read(tmp_path, "one")
    with pytest.raises(IntegrityError, match="count limit"):
        budget.read(tmp_path, "absent")
    assert budget.count == 2 and budget.size == 2


@pytest.mark.parametrize("runtime", ["direct", "governed"])
@pytest.mark.parametrize("kind", ["nodes", "depth"])
def test_manifest_structure_refused_before_any_decoder(
    tmp_path, monkeypatch, runtime, kind
):
    raw = b"[" + b"0," * 40 + b"0]" if kind == "nodes" else b"[" * 10 + b"]" * 10
    (tmp_path / "apizr-repository-rest.json").write_bytes(raw)
    monkeypatch.setattr(admission, "MAX_JSON_NODES", 32)
    monkeypatch.setattr(admission, "MAX_JSON_DEPTH", 8)

    decodes = []

    def unexpected(*args, **kwargs):
        decodes.append(args)
        pytest.fail("Unadmitted JSON reached the decoder")

    with monkeypatch.context() as scoped:
        scoped.setattr(json, "loads", unexpected)
        if runtime == "governed":
            from apizr.repository_interfaces.model import RestManifest

            scoped.setattr(RestManifest, "model_validate_json", unexpected)
        with pytest.raises((IntegrityError, RuntimeError, ValueError)):
            if runtime == "direct":
                load_bundle(tmp_path, "rest")
            else:
                GovernedRuntime(tmp_path, "rest")
    assert decodes == []


@pytest.mark.parametrize("runtime", ["direct", "governed"])
def test_metadata_structure_refused_before_decoding_or_import(
    tmp_path, monkeypatch, inputs, runtime
):
    if runtime == "direct":
        write_bundle(tmp_path, render_repository_bundle(*inputs, interface="rest"))
    else:
        governed_bundle(tmp_path)
    target = tmp_path / "repository-interface.json"
    raw = b"[" * (admission.MAX_JSON_DEPTH + 1) + b"]" * (admission.MAX_JSON_DEPTH + 1)
    target.write_bytes(raw)
    manifest_path = tmp_path / "apizr-repository-rest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["artifacts"][target.name] = digest(raw)
    if runtime == "governed":
        bridge_path = tmp_path / "execution/bundle.json"
        bridge = json.loads(bridge_path.read_bytes())
        bridge["artifacts"][target.name] = digest(raw)
        bridge_raw = json.dumps(bridge).encode()
        bridge_path.write_bytes(bridge_raw)
        manifest["artifacts"]["execution/bundle.json"] = digest(bridge_raw)
    manifest_path.write_text(json.dumps(manifest))
    original = json.loads
    decodes = []

    def observed(value, *args, **kwargs):
        if value == raw:
            decodes.append(value)
            raise ValueError("Decoder received unadmitted metadata")
        return original(value, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(json, "loads", observed)
        if runtime == "governed":
            from apizr.repository_interfaces.model import RepositoryInterface

            scoped.setattr(RepositoryInterface, "model_validate_json", observed)
        with pytest.raises(RuntimeError):
            if runtime == "direct":
                load_bundle(tmp_path, "rest")
            else:
                GovernedRuntime(tmp_path, "rest")
    assert decodes == []


@pytest.mark.parametrize("runtime", ["direct", "governed", "worker"])
@pytest.mark.parametrize("limit", ["bytes", "count"])
def test_all_runtime_contracts_charge_the_whole_retained_set(
    tmp_path, monkeypatch, inputs, runtime, limit
):
    if runtime == "worker":
        plan, exposure, sources, _ = planned()
        stage(tmp_path, plan, exposure, sources)
        first = (tmp_path / "repository-interface.json").read_bytes()
        byte_limit = len(first) + len(exposure) + sum(map(len, sources.values())) - 1
        count = 2
        request = Request(plan=plan, plan_digest=model_digest(plan), arguments={})
    else:
        if runtime == "direct":
            write_bundle(tmp_path, render_repository_bundle(*inputs, interface="rest"))
        else:
            governed_bundle(tmp_path)
        first = (tmp_path / "apizr-repository-rest.json").read_bytes()
        count = len(json.loads(first)["artifacts"])
        byte_limit = len(first)
    monkeypatch.setattr(
        admission,
        "MAX_BUNDLE_BYTES" if limit == "bytes" else "MAX_BUNDLE_ARTIFACTS",
        byte_limit if limit == "bytes" else count,
    )
    original_install = RepositoryLoader.install
    imports = []

    def unexpected(self):
        imports.append(self)
        pytest.fail("Project imports must follow aggregate admission")

    monkeypatch.setattr(RepositoryLoader, "install", unexpected)
    try:
        if runtime == "worker":
            assert handle(request, tmp_path).status == "binding_failed"
        else:
            with pytest.raises(RuntimeError):
                if runtime == "direct":
                    load_bundle(tmp_path, "rest")
                else:
                    GovernedRuntime(tmp_path, "rest")
    finally:
        monkeypatch.setattr(RepositoryLoader, "install", original_install)
    assert imports == []
    assert "shop" not in sys.modules and "sample" not in sys.modules


def test_changed_source_size_is_bounded_again_before_compile(tmp_path, monkeypatch):
    path = tmp_path / "source.py"
    original = b"value = 1\n"
    path.write_bytes(original + b"raise AssertionError('must never compile')\n")
    loader = RepositoryLoader(
        tmp_path,
        [
            {
                "module": "bounded_source",
                "bundle_path": "source.py",
                "size": len(original),
                "source_digest": digest(original),
                "is_package": False,
            }
        ],
    )
    limits = []

    def observed(root, name, limit=None):
        limits.append(limit)
        return admission.read_artifact(root, name, limit)

    monkeypatch.setattr("apizr.repository_interfaces.runtime.read_artifact", observed)
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader("bounded_source", loader)
    )
    with pytest.raises(IntegrityError):
        loader.exec_module(module)
    assert not hasattr(module, "value")
    assert limits == [len(original)]


def test_generation_admission_and_opaque_json_resources(monkeypatch):
    monkeypatch.setattr(admission, "MAX_BUNDLE_BYTES", 8)
    admission.check_bundle({"one": b"1234", "two": b"5678"})
    with pytest.raises(ValueError, match="byte limit"):
        admission.check_bundle({"one": b"1234", "two": b"56789"})
    monkeypatch.setattr(admission, "MAX_BUNDLE_ARTIFACTS", 1)
    with pytest.raises(ValueError, match="count limit"):
        admission.check_bundle({"one": b"", "two": b""})
    admission.check_bundle({"source/data.json": b"\xff\xfe"})
    with pytest.raises(ValueError):
        admission.check_bundle({"metadata.json": b"\xff\xfe"})


@pytest.mark.parametrize("governed", [False, True])
def test_renderer_refuses_unloadable_bundle(monkeypatch, inputs, governed):
    from governed_repository.helpers import inputs as governed_inputs

    from apizr.execution.policy import ExecutionPolicy

    monkeypatch.setattr(admission, "MAX_BUNDLE_ARTIFACTS", 1)
    with pytest.raises(ValueError, match="count limit"):
        render_repository_bundle(
            *(governed_inputs() if governed else inputs),
            interface="rest",
            execution_policy=ExecutionPolicy() if governed else None,
        )


@pytest.mark.parametrize("transport", ["rest", "mcp"])
@pytest.mark.parametrize("governed", [False, True])
def test_emitted_admission_has_no_core_dependency_and_enforces_limits(
    tmp_path, inputs, transport, governed
):
    if governed:
        governed_bundle(tmp_path, transport)
        module = "apizr_governed.repository_interfaces.artifacts"
    else:
        write_bundle(tmp_path, render_repository_bundle(*inputs, interface=transport))
        module = "apizr_repository_artifacts"
    probe = """import importlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
def audit(event, args):
    if event == 'import' and args[0].startswith('apizr.'):
        raise AssertionError('Core dependency in standalone admission')
sys.addaudithook(audit)
admission = importlib.import_module(sys.argv[2])
manifest = 'apizr-repository-' + sys.argv[3] + '.json'
admission.MAX_BUNDLE_BYTES = (root / manifest).stat().st_size
budget = admission.BundleBudget()
members = json.loads(budget.read(root, manifest))['artifacts']
try:
    budget.read_many(root, members)
except admission.IntegrityError:
    pass
else:
    raise AssertionError('Aggregate limit was bypassed')
raw = b'[' * 129 + b']' * 129
(root / 'bomb.json').write_bytes(raw)
try:
    admission.read_artifact(root, 'bomb.json')
except ValueError:
    pass
else:
    raise AssertionError('JSON structure limit was bypassed')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(tmp_path), module, transport],
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()

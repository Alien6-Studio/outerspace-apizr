"""Preparation refuses incomplete closures, publication races and source builds."""

import io
import json
import shutil
import sys
import tarfile
import time
from pathlib import Path
from threading import Event

import pytest

from apizr.plugins.artifacts.models import PluginError
from apizr.plugins.preparation import operations, resolver, selection, target
from apizr.plugins.preparation.models import (
    Artifact,
    Control,
    Pin,
    PreparationError,
    PreparationResult,
)
from apizr.plugins.preparation.process import Completed
from apizr.plugins.preparation.requirements import parse_resolver_lock


@pytest.fixture
def inputs(chain):
    plugin, digest, lock, house = chain
    shutil.copyfile(plugin, house / plugin.name)
    return plugin, digest, lock, house


def prepare(inputs, tmp_path, **options):
    _, _, lock, house = inputs
    return operations.prepare_plugin(
        "local-probe",
        "1.0",
        python=Path(sys.executable),
        platform="native",
        output_dir=tmp_path / "prepared",
        wheelhouse=house,
        requirements=lock,
        **options,
    )


def test_hostile_sdist_cannot_launch_a_build_backend(inputs, tmp_path):
    _, _, lock, house = inputs
    marker = tmp_path / "BUILD-MUST-NOT-RUN"
    source = f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('must never execute')\n".encode()
    with tarfile.open(house / "locked-leaf-1.0.tar.gz", "w:gz") as archive:
        member = tarfile.TarInfo("locked-leaf-1.0/setup.py")
        member.size = len(source)
        archive.addfile(member, io.BytesIO(source))
    next(house.glob("locked_leaf*.whl")).unlink()
    lock.unlink()
    result = operations.prepare_plugin(
        "local-probe",
        "1.0",
        python=Path(sys.executable),
        platform="native",
        output_dir=tmp_path / "prepared",
        wheelhouse=house,
    )
    assert (
        result.state == "refused"
        and result.diagnostics[0].reason == "compatible_wheel_unavailable"
    ), result
    assert result.diagnostics[0].distribution == "locked-leaf"
    assert result.target is not None and not marker.exists()
    assert not (tmp_path / "prepared").exists()


@pytest.mark.parametrize(
    "case,reason",
    [
        ("no_plugin", "plugin_not_in_resolver_lock"),
        ("closure_changed", "resolver_lock_mismatch"),
        ("publication_race", "output_exists"),
        ("rename_failure", "preparation_io_refused"),
        ("cancel_after_resolution", "preparation_cancelled"),
        ("interrupt", "preparation_cancelled"),
        ("artifact_error", "invalid_wheel"),
    ],
)
def test_failed_transaction_has_no_partial_publication(
    inputs, tmp_path, monkeypatch, case, reason
):
    cancel = Event()
    if case == "no_plugin":
        lock = inputs[2]
        lock.write_text(
            "\n".join(
                line
                for line in lock.read_text().splitlines()
                if not line.startswith("local-probe")
            )
        )
    elif case == "closure_changed":
        monkeypatch.setattr(resolver, "resolve", lambda *a: ())
    elif case == "publication_race":
        real_mkdir = operations.os.mkdir

        def raced(path, *args, **kwargs):
            if path == "prepared":
                real_mkdir(path, *args, **kwargs)
                (tmp_path / "prepared/sentinel").write_text("concurrent owner")
            return real_mkdir(path, *args, **kwargs)

        monkeypatch.setattr(operations.os, "mkdir", raced)
    elif case == "rename_failure":

        def failed(*a, **kw):
            raise OSError("/secret-path")

        monkeypatch.setattr(operations.os, "rename", failed)
    elif case == "cancel_after_resolution":
        real_resolve = resolver.resolve

        def cancelled(*args):
            value = real_resolve(*args)
            cancel.set()
            return value

        monkeypatch.setattr(resolver, "resolve", cancelled)
    elif case == "interrupt":

        def interrupted(*args):
            raise KeyboardInterrupt()

        monkeypatch.setattr(target, "probe", interrupted)
    else:

        def invalid(*args):
            raise PluginError("invalid_wheel")

        monkeypatch.setattr(selection, "snapshot", invalid)
    result = prepare(inputs, tmp_path, cancel=cancel)
    assert result.state != "prepared"
    assert result.diagnostics[0].reason == reason, result
    assert not list(tmp_path.glob(".apizr-preparation-*"))
    if case == "publication_race":
        assert {p.name for p in (tmp_path / "prepared").iterdir()} == {"sentinel"}
    else:
        assert not (tmp_path / "prepared").exists()
    assert str(tmp_path) not in result.model_dump_json()


@pytest.mark.parametrize(
    "options,reason",
    [
        ({"timeout_ms": 0}, "invalid_preparation_limits"),
        ({"timeout_ms": True}, "invalid_preparation_limits"),
        ({"version": "wild*"}, "invalid_preparation_input"),
        ({}, "artifact_source_required"),
    ],
)
def test_invalid_request_has_no_side_effects(tmp_path, options, reason):
    kwargs = {
        "name": "example",
        "version": "1.0",
        "python": Path(sys.executable),
        "platform": "native",
        "output_dir": tmp_path / "prepared",
        **options,
    }
    result = operations.prepare_plugin(**kwargs)
    assert result.diagnostics[0].reason == reason and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "bound", ["MAX_CANDIDATES", "MAX_TOTAL_BYTES", "MAX_TOTAL_EXPANDED_BYTES"]
)
def test_snapshot_bounds_are_enforced_before_resolution(
    inputs, tmp_path, monkeypatch, bound
):
    monkeypatch.setattr(selection, bound, 0)
    result = prepare(inputs, tmp_path)
    assert result.diagnostics[0].reason == (
        "too_many_artifact_candidates"
        if bound == "MAX_CANDIDATES"
        else "wheelhouse_too_large"
    )
    assert not (tmp_path / "prepared").exists()


def test_result_contract_rejects_inconsistent_artifact_evidence(inputs, tmp_path):
    with pytest.raises(ValueError):
        Pin(name="EXAMPLE", version="1.0")
    with pytest.raises(ValueError):
        Artifact(
            name="example",
            version="1.0",
            filename="example-1.0-py3-none-any.whl",
            sha256="a" * 64,
            size=1,
            admitted_hashes=("b" * 64,),
        )
    result = prepare(inputs, tmp_path)
    data = result.model_dump(by_alias=True)
    data["artifacts"] = tuple(reversed(data["artifacts"]))
    with pytest.raises(ValueError, match="inconsistent_preparation"):
        PreparationResult.model_validate(data)


@pytest.mark.parametrize(
    "case",
    [
        "unsupported_version",
        "missing_tool",
        "relative_tool",
        "invalid_url",
        "query_url",
    ],
)
def test_resolver_configuration_is_explicit_and_redacted(tmp_path, monkeypatch, case):
    control = Control(time.monotonic() + 5)
    native = target.probe(Path(sys.executable), "native", tmp_path, control)
    executable, index = Path(sys.executable), None
    reason = "resolver_unavailable"
    if case == "unsupported_version":
        monkeypatch.setattr(
            resolver, "run", lambda *a, **kw: Completed(0, b"uv 0.99.0\n", b"")
        )
        reason = "resolver_version_unsupported"
    elif case == "missing_tool":
        executable = None
        monkeypatch.setattr(resolver.shutil, "which", lambda *a: None)
    elif case == "relative_tool":
        executable = Path("uv")
    else:
        index = (
            "https://example.test/simple?token=private"
            if case == "query_url"
            else "https://user:secret@example.test/simple?token=private"
        )
        reason = "invalid_index_url"
    with pytest.raises(PreparationError, match=reason):
        resolver.configure(
            executable, Path(sys.executable), native, None, index, tmp_path, control
        )


def test_network_resolution_preserves_whole_evidence_and_requires_wheels(
    tmp_path, monkeypatch
):
    control = Control(time.monotonic() + 5)
    native = target.probe(Path(sys.executable), "native", tmp_path, control)
    tool = resolver.Resolver(
        "/exact/uv",
        "uv 0.12.0",
        Path(sys.executable),
        native,
        None,
        "https://index.example.test/simple",
    )
    captured = []

    def invoke(args, work, control, **kwargs):
        captured.append((args, kwargs))
        return Completed(0, b"machine-evidence", b"private-diagnostic")

    monkeypatch.setattr(resolver, "run", invoke)
    assert (
        resolver.compile_evidence(
            tool, b"example==1.0\n", tmp_path, control, candidates=True
        )
        == b"machine-evidence"
    )
    args, options = captured[0]
    assert "--only-binary" in args and ":all:" in args and "--universal" in args
    assert (
        "--no-deps" in args
        and "--no-sources" in args
        and "--no-python-downloads" in args
    )
    assert "--default-index" in args and "disabled" in args
    assert options["environment"]["HOME"] == str(tmp_path)
    for diagnostic, reason, name in [
        (
            b"Because private-package==1.0 has no usable wheels secret/path",
            "compatible_wheel_unavailable",
            "private-package",
        ),
        (
            b"Because missing was not found in the package registry",
            "compatible_wheel_unavailable",
            "missing",
        ),
        (
            b"unrecognized resolver error: secret-token at /private/location",
            "resolver_refused",
            None,
        ),
    ]:
        monkeypatch.setattr(
            resolver,
            "run",
            lambda *a, diagnostic=diagnostic, **kw: Completed(1, b"", diagnostic),
        )
        with pytest.raises(PreparationError) as caught:
            resolver.compile_evidence(tool, b"example==1.0\n", tmp_path, control)
        assert (
            caught.value.diagnostic.reason == reason
            and caught.value.diagnostic.distribution == name
        )
        assert "secret" not in caught.value.diagnostic.model_dump_json()
    monkeypatch.setattr(resolver, "compile_evidence", lambda *a, **kw: b"x" * 5)
    monkeypatch.setattr(resolver, "MAX_REQUIREMENTS_BYTES", 4)
    with pytest.raises(PreparationError, match="resolver_lock_too_large"):
        resolver.resolve(tool, "example", "1.0", tmp_path, control)


def test_network_workflow_validates_artifact_evidence_before_offline_closure(
    inputs, tmp_path, monkeypatch
):
    # Resolver protocol is substituted, but real snapshot/selection/closure and publication run.
    real_compile = resolver.compile_evidence

    def compile_evidence(tool, pins, work, control, **options):
        if not options.get("candidates"):
            return real_compile(tool, pins, work, control, **options)
        assert tool.index_url == "https://index.example.test/simple"
        lines = ['lock-version="1.0"', 'created-by="uv"']
        for pin in parse_resolver_lock(inputs[2].read_bytes()):
            wheel = next(tool.wheelhouse.glob(pin.name.replace("-", "_") + "-*.whl"))
            lines.extend(
                [
                    "[[packages]]",
                    f'name="{pin.name}"',
                    f'version="{pin.version}"',
                    f'wheels=[{{path={json.dumps(str(wheel))},hashes={{sha256="{pin.hashes[0]}"}}}}]',
                ]
            )
        return "\n".join(lines).encode()

    monkeypatch.setattr(resolver, "compile_evidence", compile_evidence)
    result = prepare(inputs, tmp_path, index_url="https://index.example.test/simple")
    assert result.state == "prepared", result

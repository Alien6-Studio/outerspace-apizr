"""Targets record the chosen interpreter, including macOS Intel and Linux wheels."""

import builtins
import json
import sys
import time
from pathlib import Path

import pytest
from packaging.tags import Tag

from apizr.plugins.lock.models import Target
from apizr.plugins.preparation import target
from apizr.plugins.preparation.models import Control, PreparationError
from apizr.plugins.preparation.process import Completed


def measured(
    system="darwin", machine="x86_64", platform="macosx-15.0-x86_64", **changes
):
    return {
        "target": {
            "implementation": "cpython",
            "python": "3.14.0",
            "platform": platform,
            "machine": machine,
            "abi": "cpython-314-darwin",
            **changes,
        },
        "system": system,
        "libc": ["glibc", "2.39"],
    }


def probe(data, tmp_path, monkeypatch, platform="native", code=0):
    monkeypatch.setattr(
        target,
        "run",
        lambda *args, **kwargs: Completed(
            code, json.dumps(data).encode(), b"secret-error-path"
        ),
    )
    return target.probe(
        Path(sys.executable), platform, tmp_path, Control(time.monotonic() + 5)
    )


@pytest.mark.parametrize(
    "system,machine,platform,resolver_platform",
    [
        ("darwin", "x86_64", "macosx-15.0-x86_64", "x86_64-apple-darwin"),
        ("darwin", "arm64", "macosx-15.0-arm64", "aarch64-apple-darwin"),
        ("linux", "x86_64", "linux-x86_64", "x86_64-manylinux_2_39"),
        ("linux", "aarch64", "linux-aarch64", "aarch64-manylinux_2_39"),
    ],
)
def test_measured_native_targets_are_explicit(
    system, machine, platform, resolver_platform, tmp_path, monkeypatch
):
    result = probe(
        measured(system, machine, platform),
        tmp_path,
        monkeypatch,
        platform=resolver_platform,
    )
    assert result.identity.python == "3.14.0" and result.identity.machine == machine
    assert result.resolver_platform == resolver_platform
    assert result.environment == (
        {"MACOSX_DEPLOYMENT_TARGET": "15.0"} if system == "darwin" else {}
    )


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        measured(implementation="pypy"),
        measured(abi=""),
        measured(platform="macosx-15.0-arm64"),
        measured(platform="macosx-unknown"),
        measured(system="win32", machine="AMD64", platform="win-amd64"),
        {**measured(system="linux", platform="linux-x86_64"), "libc": ["musl", "1.2"]},
        {
            **measured(system="linux", platform="linux-x86_64"),
            "libc": ["glibc", "unexpected"],
        },
        {
            **measured(system="linux", platform="linux-x86_64"),
            "libc": ["glibc", "2.27"],
        },
        measured(python="3.15.0"),
    ],
)
def test_unproven_target_measurements_fail_closed(data, tmp_path, monkeypatch):
    with pytest.raises(PreparationError, match="target_invalid"):
        probe(data, tmp_path, monkeypatch)


def test_non_executable_or_failed_interpreter_has_specific_diagnostic(
    tmp_path, monkeypatch
):
    with pytest.raises(PreparationError, match="interpreter_unavailable"):
        probe(measured(), tmp_path, monkeypatch, code=1)
    monkeypatch.setattr(target.os, "access", lambda *args: False)
    with pytest.raises(PreparationError, match="interpreter_unavailable"):
        probe(measured(), tmp_path, monkeypatch)


def test_linux_platform_priority_uses_native_host_but_explicit_python(monkeypatch):
    import packaging.tags

    monkeypatch.setattr(target.sys, "platform", "linux")
    monkeypatch.setattr(target.host_platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        packaging.tags,
        "platform_tags",
        lambda: iter(
            ["manylinux_2_39_x86_64", "manylinux_2_17_x86_64", "linux_x86_64"]
        ),
    )
    identity = Target.model_validate(
        measured(system="linux", platform="linux-x86_64")["target"]
    )
    tags = target.supported_tags(identity)
    assert (
        tags["cp314-cp314-manylinux_2_39_x86_64"]
        < tags["cp314-cp314-manylinux_2_17_x86_64"]
        < tags["cp311-abi3-manylinux_2_39_x86_64"]
    )
    with pytest.raises(PreparationError, match="target_invalid"):
        target.supported_tags(identity.model_copy(update={"machine": "arm64"}))


def test_missing_optional_preparation_extra_does_not_break_core_imports(monkeypatch):
    real_import = builtins.__import__

    def without_packaging(name, *args, **kwargs):
        if name.startswith("packaging"):
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_packaging)
    with pytest.raises(PreparationError, match="preparation_extra_required"):
        target.supported_tags(Target.model_validate(measured()["target"]))


def test_tag_expansion_is_bounded(monkeypatch):
    import packaging.tags

    monkeypatch.setattr(
        packaging.tags,
        "cpython_tags",
        lambda *a, **kw: (Tag(f"cp{i}", "none", "any") for i in range(16385)),
    )
    with pytest.raises(PreparationError, match="target_invalid"):
        target.supported_tags(Target.model_validate(measured()["target"]))

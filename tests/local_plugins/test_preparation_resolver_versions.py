"""Version qualification remains explicit and rejects unknown resolver semantics."""

import sys
import time
from pathlib import Path

import pytest

from apizr.plugins.lock.models import Target
from apizr.plugins.preparation.models import Control, PreparationError
from apizr.plugins.preparation.process import Completed
from apizr.plugins.preparation.resolver import configure
from apizr.plugins.preparation.target import NativeTarget


@pytest.mark.parametrize(
    "output,code,accepted",
    [
        (b"uv 0.12.0\n", 0, "uv 0.12.0"),
        (b"uv 0.12.17 (Homebrew build)\n", 0, "uv 0.12.17"),
        (b"uv 0.13.0\n", 0, "uv 0.13.0"),
        (b"uv 0.13.1 (62faed335)\n", 0, "uv 0.13.1"),
        (b"uv 0.14.0\n", 0, None),
        (b"uv 1.13.1\n", 0, None),
        (b"uv 0.11.0\n", 0, None),
        (b"uv 0.13.1rc1\n", 0, None),
        (b"uv 0.13.1+unqualified\n", 0, None),
        (b"unexpected private output", 0, None),
        (b"uv " + b"9" * 5000 + b".13.0\n", 0, None),
        (b"uv 0.13.1\n", 1, None),
    ],
)
def test_only_qualified_stable_series_are_measured(
    monkeypatch, tmp_path, output, code, accepted
):
    monkeypatch.setattr(
        "apizr.plugins.preparation.resolver.run",
        lambda *a, **k: Completed(code, output, b"private"),
    )
    native = NativeTarget(
        Target(
            implementation="cpython",
            python="3.14.0",
            platform="linux-x86_64",
            machine="x86_64",
            abi="cpython-314-x86_64-linux-gnu",
        ),
        "x86_64-manylinux_2_41",
        {},
    )
    arguments = (
        Path(sys.executable),
        Path(sys.executable),
        native,
        None,
        None,
        tmp_path,
        Control(time.monotonic() + 5),
    )
    if accepted:
        assert configure(*arguments).version == accepted
    else:
        with pytest.raises(PreparationError, match="^resolver_version_unsupported$"):
            configure(*arguments)


def test_native_glibc_resolution_never_substitutes_an_older_platform(
    tmp_path, monkeypatch
):
    from apizr.plugins.preparation.resolver import Resolver, compile_evidence

    native = NativeTarget(
        Target(
            implementation="cpython",
            python="3.14.0",
            platform="linux-x86_64",
            machine="x86_64",
            abi="cpython-314-x86_64-linux-gnu",
        ),
        "native-x86_64-glibc-2.41",
        {},
        True,
    )
    calls = []
    monkeypatch.setattr(
        "apizr.plugins.preparation.resolver.run",
        lambda args, *a, **kw: (
            calls.append(args) or Completed(0, b"retained-evidence", b"")
        ),
    )
    tool = Resolver(
        "/absolute/uv", "uv 0.13.1", Path(sys.executable), native, tmp_path, None
    )
    assert (
        compile_evidence(
            tool, b"example==1.0\n", tmp_path, Control(time.monotonic() + 5)
        )
        == b"retained-evidence"
    )
    assert "--python-platform" not in calls[0]
    assert "--python" in calls[0] and "--no-python-downloads" in calls[0]
    assert "--only-binary" in calls[0] and "--generate-hashes" in calls[0]


def test_unsupported_resolver_cli_names_the_qualified_series(
    tmp_path, monkeypatch, capsys
):
    from apizr.cli import main
    from apizr.plugins.preparation.models import Diagnostic, PreparationResult

    refused = PreparationResult(
        state="refused",
        diagnostics=(Diagnostic(reason="resolver_version_unsupported"),),
    )
    monkeypatch.setattr(
        "apizr.cli.commands.plugin_preparation.prepare_plugin", lambda *a, **kw: refused
    )
    assert (
        main(
            [
                "plugins",
                "prepare",
                "example",
                "--version",
                "1.0",
                "--python",
                sys.executable,
                "--platform",
                "native",
                "--output-dir",
                str(tmp_path / "unused"),
                "--json",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert "uv 0.12.x or 0.13.x" in captured.err and "--uv" in captured.err
    assert '"resolver_version_unsupported"' in captured.out
    assert not (tmp_path / "unused").exists()

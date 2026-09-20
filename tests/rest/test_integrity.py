import importlib.machinery
import importlib.util
from types import SimpleNamespace

import pytest

from apizr.generators.rest import generate
from apizr.inspection import inspect_source

from .helpers import application


def test_changed_source_fails_before_import_or_side_effect(tmp_path):
    root = tmp_path / "bundle"
    source = b"def f(x: int): return x\n"
    generate(inspect_source(source, module_name="tampered"), source, root)
    marker = tmp_path / "executed"
    (root / "source/tampered.py").write_text(
        f"open({str(marker)!r}, 'w').write('bad')\n"
    )
    spec = importlib.util.spec_from_file_location("tampered_adapter", root / "app.py")
    module = importlib.util.module_from_spec(spec)
    with pytest.raises(RuntimeError, match="source digest mismatch"):
        spec.loader.exec_module(module)
    assert not marker.exists()


def test_verified_bytes_are_used_even_if_source_changes_between_read_and_import(
    tmp_path, monkeypatch
):
    original = importlib.machinery.SourceFileLoader.exec_module
    marker = tmp_path / "executed"

    def raced(loader, module):
        if module.__name__ == "rest_sample":
            (tmp_path / "bundle/source/rest_sample.py").write_text(
                f"open({str(marker)!r}, 'w').write('bad')"
            )
        return original(loader, module)

    monkeypatch.setattr(importlib.machinery.SourceFileLoader, "exec_module", raced)
    with application(tmp_path / "bundle", "def f(): return 42") as adapter:
        assert adapter.sys.modules["rest_sample"].f() == 42
    assert not marker.exists()


@pytest.mark.parametrize(
    "replacement",
    [
        "missing",
        "not_callable",
        "renamed_parameter",
        "async",
        "generator",
        "async_generator",
        "variadic",
        "default",
    ],
)
def test_contradictory_runtime_binding_fails_startup(
    tmp_path, monkeypatch, replacement
):
    original = importlib.machinery.SourceFileLoader.exec_module

    def alternate(y):
        return y

    async def asynchronous(x):
        return x

    def generator(x):
        yield x

    async def async_generator(x):
        yield x

    def variadic(*x):
        return x

    def default(x=1):
        return x

    alternatives = {
        "not_callable": 42,
        "renamed_parameter": alternate,
        "async": asynchronous,
        "generator": generator,
        "async_generator": async_generator,
        "variadic": variadic,
        "default": default,
    }

    def changed(loader, module):
        result = original(loader, module)
        if module.__name__ == "rest_sample":
            if replacement == "missing":
                del module.f
            else:
                module.f = alternatives[replacement]
        return result

    monkeypatch.setattr(importlib.machinery.SourceFileLoader, "exec_module", changed)
    with pytest.raises(RuntimeError, match="function|mismatch|generator|variadic"):
        with application(tmp_path / "bundle", "def f(x: int): return x"):
            pytest.fail("Contradictory binding was allowed to start")


def test_binding_verification_does_not_resolve_annotations(tmp_path):
    with application(
        tmp_path / "bundle",
        "from __future__ import annotations\ndef f(x: int) -> Missing: return x",
    ) as adapter:
        function = adapter.sys.modules["rest_sample"].f
        function.__annotations__ = {"x": "expression_that_must_not_be_evaluated()"}
        assert (
            adapter.verify_binding(
                SimpleNamespace(f=function), adapter.PLAN["endpoints"][0]
            )
            is function
        )


def test_existing_logical_module_or_parent_is_not_silently_reused(tmp_path):
    for logical, suffix in [("json", "module"), ("json.business", "package")]:
        with pytest.raises(RuntimeError, match="already loaded|conflicts"):
            with application(
                tmp_path / suffix, "def f(): return 1", module_name=logical
            ):
                pytest.fail("An existing unrelated module was reused")

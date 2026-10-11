import builtins
import importlib
import os
import socket
import subprocess
import typing

import pytest

from apizr.generators.mcp.generator import render as mcp
from apizr.generators.rest.generator import render as rest
from apizr.inspection import inspect_source, text_report
from apizr.readiness import assess

from .test_static import MINIMAL, NESTED


@pytest.mark.parametrize(
    "source",
    [
        MINIMAL,
        NESTED,
        MINIMAL.replace("value: int", "value: __import__('hostile').execute()"),
    ],
)
def test_inspection_readiness_and_schema_have_no_runtime_effects(monkeypatch, source):
    original_import = builtins.__import__
    original_import_module = importlib.import_module

    def guarded_import(name, *args, **kwargs):
        assert name not in {"typed_purity", "hostile"}
        return original_import(name, *args, **kwargs)

    def guarded_import_module(name, *args, **kwargs):
        assert name not in {"typed_purity", "hostile"}
        return original_import_module(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("Static contract analysis caused a runtime effect")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(importlib, "import_module", guarded_import_module)
    monkeypatch.setattr(typing, "get_type_hints", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    inspected = inspect_source(source, module_name="typed_purity")
    assert assess(inspected.capability_ir, source) == inspected.readiness
    if inspected.readiness.assessments[0].can_generate_interface:
        for renderer in (rest, mcp):
            assert renderer(inspected, source.encode())
    else:
        assert "Annotation calls" in text_report(inspected)

import importlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apizr.main import convert
from apizr.modules.code_analyzr.analyzr.astAnalyzr import AstAnalyzr
from apizr.modules.code_analyzr.configuration import CodeAnalyzrConfiguration

CORPUS = Path(__file__).resolve().parents[1] / "fixtures/characterization"


def analyze(source, **configuration):
    return AstAnalyzr(CodeAnalyzrConfiguration(**configuration), source).get_analyse()


def corpus(name):
    return json.loads((CORPUS / name).read_text(encoding="utf-8"))


@contextmanager
def runtime(output, module="contract_source_api"):
    """Import trusted test fixtures only; clean modules even after import failures."""
    before = set(sys.modules)
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(output))
        importlib.invalidate_caches()
        try:
            yield TestClient(
                importlib.import_module(module).app, raise_server_exceptions=False
            )
        finally:
            for name in set(sys.modules) - before:
                filename = getattr(sys.modules[name], "__file__", None)
                if filename and Path(filename).resolve().is_relative_to(
                    output.resolve()
                ):
                    sys.modules.pop(name, None)


def generate(root, source, **options):
    path = root / "contract_source.py"
    path.write_text(source, encoding="utf-8")
    output = root / "output"
    convert(path, output, **options)
    return output


def contents(directory):
    return {
        str(p.relative_to(directory)): p.read_bytes()
        for p in directory.rglob("*")
        if p.is_file()
    }

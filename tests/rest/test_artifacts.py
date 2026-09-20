import hashlib
import json

import nbformat
import pytest

from apizr.capabilities import document_digest
from apizr.capability_notebooks import inspect_notebook_bytes
from apizr.generators.rest import plan, render
from apizr.inspection import Inspection, inspect_source
from apizr.readiness import assess, report_digest


def notebook_inspection(raw):
    exported = inspect_notebook_bytes(raw, module_name="notebook_example")
    executable = exported.python_source.encode()
    readiness = assess(exported.document, executable)
    return Inspection(
        capability_ir=exported.document,
        ir_digest=document_digest(exported.document),
        readiness=readiness,
        readiness_digest=report_digest(readiness),
    ), executable


def test_manifest_hashes_every_artifact_except_itself_and_links_contracts():
    source = b"def f(x: int) -> int: return x\n"
    inspection = inspect_source(source, module_name="project.pricing")
    artifacts = render(inspection, source)
    assert list(artifacts) == sorted(artifacts)
    assert set(artifacts) == {
        "app.py",
        "apizr-rest.json",
        "capability-ir.json",
        "readiness.json",
        "openapi.json",
        "requirements.txt",
        "source/project/__init__.py",
        "source/project/pricing.py",
    }
    manifest = json.loads(artifacts["apizr-rest.json"])
    assert manifest["schema_version"] == "apizr.rest/v1"
    assert set(manifest["artifacts"]) == set(artifacts) - {"apizr-rest.json"}
    for name, digest in manifest["artifacts"].items():
        assert digest == {
            "algorithm": "sha256",
            "value": hashlib.sha256(artifacts[name]).hexdigest(),
        }
    assert manifest["ir_digest"] == inspection.ir_digest.model_dump()
    assert manifest["readiness_digest"] == inspection.readiness_digest.model_dump()
    assert artifacts["source/project/pricing.py"] == source
    assert artifacts["source/project/__init__.py"] == b""
    assert b"/Users/" not in artifacts["apizr-rest.json"]
    assert b"/tmp/" not in artifacts["openapi.json"]
    assert artifacts == render(inspection, source)


def test_notebook_binds_original_and_executable_bytes():
    notebook = nbformat.v4.new_notebook(
        cells=[nbformat.v4.new_code_cell("def f(x: int) -> int: return x")]
    )
    raw = nbformat.writes(notebook).encode()
    inspection, executable = notebook_inspection(raw)
    artifacts = render(inspection, raw, executable=executable)
    assert artifacts["notebook.ipynb"] == raw
    assert artifacts["source/notebook_example.py"] == executable
    assert (
        json.loads(artifacts["apizr-rest.json"])["executable_digest"]
        == inspection.capability_ir.source.transformed_digest.model_dump()
    )
    for changed in (None, executable + b"\n"):
        with pytest.raises(ValueError, match="Executable bytes"):
            plan(inspection, raw, executable=changed)


def test_init_named_source_is_never_overwritten_by_package_stub():
    source = b"def f(): return 1\n"
    artifacts = render(inspect_source(source, module_name="project.__init__"), source)
    assert artifacts["source/project/__init__.py"] == source

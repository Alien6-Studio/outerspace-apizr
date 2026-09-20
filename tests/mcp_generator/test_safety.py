import json
import sys

import pytest

from apizr.capabilities.model import Digest
from apizr.generators.mcp import generate, plan, render
from apizr.generators.mcp.runtime import create_server
from apizr.inspection import inspect_source
from apizr.interfaces.planner import GenerationRefused
from apizr.readiness import report_digest
from apizr.readiness.model import Code, Dimension, Reason


@pytest.mark.parametrize(
    "source",
    [
        "@decorator\ndef f(): pass",
        "if flag:\n def f(): pass",
        "def f(): yield 1",
        "async def f(): yield 1",
        "def f(): pass\ndef f(): pass",
        "def f(*args): pass",
        "def f(x: Callable): pass",
        "def f(x: App): pass",
        "def f(): pass\nf = other",
        "initialize()\ndef f(): pass",
        "def f(x: int = dangerous()): pass",
        "def f(x: annotation()): pass",
    ],
)
def test_noneligible_sources_never_become_tools(tmp_path, source):
    raw = source.encode()
    with pytest.raises(GenerationRefused):
        generate(inspect_source(raw, module_name="blocked"), raw, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_supplied_readiness_refusal_is_authoritative():
    source = b"def f(x: int): return x"
    inspection = inspect_source(source, module_name="policy")
    original = inspection.readiness.assessments[0]
    uncertain = Dimension(
        state="conditional",
        reasons=(Reason(code=Code.NAMESPACE, line=1),),
    )
    dimensions = original.dimensions.model_copy(update={"binding": uncertain})
    assessment = original.model_copy(
        update={
            "dimensions": dimensions,
            "state": dimensions.state,
            "can_generate_interface": False,
        }
    )
    report = inspection.readiness.model_copy(update={"assessments": (assessment,)})
    supplied = inspection.model_copy(
        update={"readiness": report, "readiness_digest": report_digest(report)}
    )
    with pytest.raises(GenerationRefused):
        plan(supplied, source)


@pytest.mark.parametrize("field", ["ir_digest", "readiness_digest"])
def test_independent_metadata_mismatch_is_rejected(field):
    source = b"def f(): pass"
    inspection = inspect_source(source, module_name="binding")
    wrong = inspection.model_copy(update={field: Digest.of_bytes(b"wrong")})
    with pytest.raises(ValueError):
        render(wrong, source)
    with pytest.raises(ValueError, match="Source bytes"):
        render(inspection, source + b"\n")


@pytest.mark.parametrize(
    "replacement",
    [
        "pass",
        "f = 1",
        "def f(y): pass",
        "def f(x, /): pass",
        "def f(x=1): pass",
        "async def f(x): pass",
        "def f(x): yield 1",
        "async def f(x): yield 1",
        "def f(*x): pass",
    ],
)
def test_legitimately_digest_bound_contradictory_runtime_fails(tmp_path, replacement):
    root = tmp_path / "bundle"
    source = b"def f(x: int): return x"
    generate(inspect_source(source, module_name="mcp_binding"), source, root)
    metadata = json.loads((root / "apizr-mcp.json").read_bytes())
    raw = replacement.encode()
    (root / "source/mcp_binding.py").write_bytes(raw)
    metadata["executable_digest"] = Digest.of_bytes(raw).model_dump()
    try:
        with pytest.raises(RuntimeError, match="function|binding|mismatch"):
            create_server(root, metadata)
    finally:
        sys.modules.pop("mcp_binding", None)


def test_selection_and_output_safety(tmp_path):
    source = b"def good(x: int): return x\ndef stream(): yield 1"
    inspection = inspect_source(source, module_name="selected")
    assert render(inspection, source, select=["good"]) == render(
        inspection, source, select=["python:selected:good", "good"]
    )
    for selection in (["stream"], ["missing"], []):
        with pytest.raises(ValueError):
            render(inspection, source, select=selection)
    root = tmp_path / "output"
    generate(inspection, source, root, select=["good"])
    before = {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }
    with pytest.raises(ValueError, match="empty"):
        generate(inspection, source, root, select=["good"])
    assert before == {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }
    (tmp_path / "link").symlink_to(root, target_is_directory=True)
    with pytest.raises(OSError):
        generate(inspection, source, tmp_path / "link/sub", select=["good"])
    with pytest.raises(ValueError, match="traversal"):
        generate(inspection, source, tmp_path / "sub/../escape", select=["good"])

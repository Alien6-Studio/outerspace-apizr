import ast

import pytest

from apizr.capabilities.model import Digest
from apizr.generators.rest import plan, render
from apizr.generators.rest.planner import GenerationRefused
from apizr.generators.rest.schema import ContractError
from apizr.inspection import inspect_source
from apizr.readiness import report_digest
from apizr.readiness.model import Code, Dimension, Reason


@pytest.mark.parametrize(
    "source",
    [
        "@decorate\ndef f(x: int): return x",
        "if flag:\n def f(): pass",
        "def f(): yield 1",
        "async def f(): yield 1",
        "def f(): pass\ndef f(): pass",
        "def f(*args): pass",
        "def f(x: Callable): pass",
        "def f(x: AppModel): pass",
        "def f(x: int): pass\nf = replacement",
        "initialize()\ndef f(x: int): pass",
        "raise RuntimeError()\ndef f(x: int): pass",
        "from typing import List as int\ndef f(x: int): pass",
    ],
)
def test_ineligible_declarations_fail_closed(source):
    raw = source.encode()
    with pytest.raises(GenerationRefused, match="Generation refused"):
        render(inspect_source(raw, module_name="blocked"), raw)


def test_selection_uses_names_or_ir_identities_only():
    source = b"def good(x: int): return x\ndef stream(): yield 1\n"
    inspection = inspect_source(source, module_name="selection")
    with pytest.raises(GenerationRefused):
        plan(inspection, source)
    first = render(inspection, source, select=["good"])
    second = render(inspection, source, select=["python:selection:good", "good"])
    assert first == second
    with pytest.raises(ValueError, match="Unknown capability"):
        plan(inspection, source, select=["not_there"])
    with pytest.raises(ValueError, match="empty"):
        plan(inspection, source, select=[])
    with pytest.raises(GenerationRefused):
        plan(inspection, source, select=["stream"])


def test_generator_honors_supplied_readiness_instead_of_reassessing_source():
    source = b"def otherwise_supported(x: int): return x"
    inspection = inspect_source(source, module_name="authority")
    original = inspection.readiness.assessments[0]
    dimensions = original.dimensions.model_copy(
        update={"binding": Dimension.assess((Reason(code=Code.NAMESPACE, line=1),))}
    )
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
    with pytest.raises(GenerationRefused, match="APIZR-READY-008"):
        plan(supplied, source)


def test_artifact_binding_rejects_mismatched_digests_sources_and_identities():
    source = b"def f(x: int): return x"
    inspection = inspect_source(source, module_name="bound")
    with pytest.raises(ValueError, match="Source bytes"):
        plan(inspection, source + b"\n")
    with pytest.raises(ValueError, match="exact inspected"):
        plan(inspection, source, executable=b"other")
    with pytest.raises(ValueError, match="digests must agree"):
        plan(
            inspection.model_copy(update={"ir_digest": Digest.of_bytes(b"other")}),
            source,
        )
    empty = inspection.readiness.model_copy(update={"assessments": ()})
    with pytest.raises(ValueError, match="identities"):
        plan(
            inspection.model_copy(
                update={"readiness": empty, "readiness_digest": report_digest(empty)}
            ),
            source,
        )
    original = inspection.readiness.assessments[0]
    changed = original.model_copy(
        update={"in_ir": False, "can_generate_interface": False}
    )
    wrong = inspection.readiness.model_copy(update={"assessments": (changed,)})
    with pytest.raises(ValueError, match="membership"):
        plan(
            inspection.model_copy(
                update={"readiness": wrong, "readiness_digest": report_digest(wrong)}
            ),
            source,
        )
    changed = original.model_copy(
        update={"source": original.source.model_copy(update={"line": 2, "end_line": 2})}
    )
    wrong = inspection.readiness.model_copy(update={"assessments": (changed,)})
    with pytest.raises(ValueError, match="evidence"):
        plan(
            inspection.model_copy(
                update={"readiness": wrong, "readiness_digest": report_digest(wrong)}
            ),
            source,
        )


def test_empty_source_is_not_a_rest_application():
    with pytest.raises(ValueError, match="No callable"):
        plan(inspect_source(b"", module_name="empty"), b"")


def test_only_ir_type_expressions_are_parsed_by_generator(monkeypatch):
    source = b"def f(x: list[int]) -> int: return sum(x)"
    inspection = inspect_source(source, module_name="boundary")
    original = ast.parse
    observed = []

    def guarded(text, *args, **kwargs):
        assert text in {"list[int]", "int"}
        observed.append(text)
        return original(text, *args, **kwargs)

    monkeypatch.setattr(ast, "parse", guarded)
    artifacts = render(inspection, source)
    assert artifacts["source/boundary.py"] == source
    assert observed == ["int", "list[int]"]


def test_inconsistent_approved_type_is_explicit_not_silently_any():
    from apizr.capabilities.types import DeclaredType
    from apizr.generators.rest.schema import lower

    with pytest.raises(ContractError, match="not self-contained"):
        lower(DeclaredType(declared="UnresolvedAlias", form="name"))

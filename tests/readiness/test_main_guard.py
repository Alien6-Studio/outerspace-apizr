"""Import-time main guards refine initialization without erasing other evidence."""

import runpy

import pytest

from apizr.inspection import inspect_source
from apizr.readiness.model import Code, State

FUNCTION = "def predict(value: int) -> int: return value * 3\n"
GUARD = 'if __name__ == "__main__":\n    train()\n'


def result(source, module="serving"):
    inspection = inspect_source(source, module_name=module)
    return next(
        item
        for item in inspection.readiness.assessments
        if item.source.symbol == "predict"
    )


def codes(assessment):
    return {reason.code for reason in assessment.dimensions.execution.reasons}


@pytest.mark.parametrize("module", ["serving", "package.serving", "package.__main__"])
def test_main_guard_is_inert_on_import_but_runs_as_script(tmp_path, module):
    marker = tmp_path / "trained"
    source = (
        "from pathlib import Path\n"
        + FUNCTION
        + f"def train(): Path({str(marker)!r}).write_text('trained')\n"
        + GUARD
    )
    assert result(source, module).state == State.READY
    assert not marker.exists()  # Inspection must never execute source.
    path = tmp_path / "serving.py"
    path.write_text(source)
    imported = runpy.run_path(str(path), run_name=module)
    assert imported["predict"](4) == 12 and not marker.exists()
    runpy.run_path(str(path), run_name="__main__")
    assert marker.read_text() == "trained"


def test_main_module_context_is_not_an_import():
    assert Code.INITIALIZATION in codes(result(FUNCTION + GUARD, "__main__"))


@pytest.mark.parametrize(
    "statement",
    [
        '__name__ = "__main__"',
        '__name__: str = "__main__"',
        'a, __name__ = (1, "__main__")',
        "del __name__",
        "import sys as __name__",
        "from sys import argv as __name__",
        "def __name__(): pass",
        "class __name__: pass",
        'globals()["__name__"] = "__main__"',
        'locals().update({"__name__": "__main__"})',
        "from unknown import *",
        'import sys\nsys.modules[__name__].__name__ = "__main__"',
        'import builtins\nbuiltins.globals()["__name__"] = "__main__"',
    ],
)
def test_shadowed_or_mutated_namespace_never_proves_main_guard(statement):
    assert Code.INITIALIZATION in codes(result(statement + "\n" + FUNCTION + GUARD))


@pytest.mark.parametrize(
    "guard",
    [
        'if __name__ == "__main__":\n    train()\nelse:\n    pass\n',
        'if __name__ != "__main__":\n    train()\n',
        'if __name__ == "serving":\n    train()\n',
        'if "__main__" == __name__:\n    train()\n',
        'if __name__ == "__main__" == other:\n    train()\n',
        "if __name__ == target:\n    train()\n",
        'if __name__ == "__main__" or True:\n    train()\n',
        'if other == "__main__":\n    train()\n',
        "if True:\n    train()\n",
        'if __name__ is "__main__":\n    train()\n',
        'while __name__ == "__main__":\n    train()\n',
    ],
)
def test_only_exact_supported_guard_is_recognized(guard):
    assert Code.INITIALIZATION in codes(result(FUNCTION + guard))


@pytest.mark.parametrize(
    "extra, expected",
    [
        ("initialize()\n", Code.INITIALIZATION),
        ("import unknown\n", Code.DEPENDENCY),
        ("__import__('unknown')\n", Code.DYNAMIC_IMPORT),
        ("def auxiliary(value=initialize()): pass\n", Code.INITIALIZATION),
    ],
)
def test_guard_does_not_waive_other_required_evidence(extra, expected):
    assert expected in codes(result(extra + FUNCTION + GUARD))


def test_guarded_definitions_remain_conditional():
    guarded = result('if __name__ == "__main__":\n    ' + FUNCTION)
    assert guarded.state == State.CONDITIONAL
    assert Code.CONDITIONAL in {r.code for r in guarded.dimensions.binding.reasons}


def test_guarded_import_and_namespace_facts_are_not_discarded():
    assert Code.DEPENDENCY in codes(
        result(FUNCTION + 'if __name__ == "__main__":\n    import unknown\n')
    )
    assert Code.INITIALIZATION in codes(
        result(FUNCTION + 'if __name__ == "__main__":\n    __name__ = "renamed"\n')
    )

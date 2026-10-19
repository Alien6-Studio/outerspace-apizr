"""Real-kernel acceptance probes shared with the installed-candidate qualification."""

import runpy
from pathlib import Path

import pytest
from qualification_scripts import implementation as qualification_script

PROOF = runpy.run_path(str(qualification_script("experiment_jupyter_proof")))


@pytest.fixture
def kernel(tmp_path):
    value = PROOF["Kernel"](tmp_path)
    try:
        yield value
    finally:
        value.close()


def test_reexecution_unsaved_cells_and_display_are_preserved(kernel):
    PROOF["prove_reexecution_unsaved_cells_and_display_are_preserved"](kernel)


def test_decorator_rebinding_and_unknown_scientific_values(kernel):
    PROOF["prove_decorator_rebinding_and_unknown_scientific_values"](kernel)


def test_interrupt_publishes_cancelled_run_and_remains_usable(kernel):
    PROOF["prove_interrupt_publishes_cancelled_run_and_remains_usable"](kernel)


def test_documented_live_notebook_is_executable(kernel):
    notebook = (
        Path(__file__).resolve().parents[2] / "examples/tracking/jupyter-capture.ipynb"
    )
    PROOF["prove_example"](kernel, notebook)

import io
import json
import socket

import pytest

from apizr.capabilities import canonical_bytes, inspect_source
from apizr.capabilities.model import Digest
from apizr.capability_notebooks import inspect_notebook
from apizr.modules.notebook_transformr.transformr.nbTransformr import NotebookTransformr


def notebook(source):
    return json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "id": "example",
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": source,
                }
            ],
        }
    ).encode()


def test_notebook_hashes_original_and_transformed_bytes_separately(
    tmp_path, monkeypatch
):
    marker = tmp_path / "must-not-exist"
    raw = notebook(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('not executed')\ndef work(x: int): return x\n"
    )
    first = tmp_path / "first.ipynb"
    second = tmp_path / "second.ipynb"
    first.write_bytes(raw)
    second.write_bytes(raw)
    monkeypatch.setattr(
        socket.socket,
        "connect",
        lambda *args: pytest.fail("network during notebook inspection"),
    )
    document = inspect_notebook(first, module_name="notebook")
    exported, _ = NotebookTransformr().convert_notebook(io.BytesIO(raw))
    expected = inspect_source(exported, module_name="notebook")
    assert document.source.kind == "notebook"
    assert document.source.digest == Digest.of_bytes(raw)
    assert document.source.transformed_digest == Digest.of_bytes(
        exported.encode("utf-8")
    )
    assert document.source.digest != document.source.transformed_digest
    assert document.capabilities == expected.capabilities
    assert canonical_bytes(document) == canonical_bytes(
        inspect_notebook(second, module_name="notebook")
    )
    assert not marker.exists()


def test_notebook_magic_rejection_is_preserved(tmp_path):
    path = tmp_path / "magic.ipynb"
    path.write_bytes(notebook("%time print('hello')"))
    with pytest.raises(ValueError, match="magics"):
        inspect_notebook(path, module_name="magic")

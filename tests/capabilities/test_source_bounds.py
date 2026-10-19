"""Bound reads and decoding before inspection, export or execution planning."""

import ast
import io
import json
import os
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apizr.capabilities import analyzer
from apizr.capabilities.inspection import inspect_file
from apizr.capabilities.source import MAX_SOURCE_BYTES, read_source
from apizr.contracts.json_budget import preflight_json
from apizr.experiments.notebook_source import code_cells
from apizr.generators.notebooks import inspect_notebook_bytes
from apizr.notebooks.exporter import NotebookTransformr


def forbidden(*args, **kwargs):
    raise AssertionError("resource-consuming operation reached before admission")


@pytest.mark.parametrize(
    "operation", [read_source, analyzer.inspect_file, inspect_file]
)
def test_large_regular_source_is_bounded_before_parsing(
    tmp_path, monkeypatch, operation
):
    path = tmp_path / "large.py"
    with path.open("wb") as file:
        file.truncate(MAX_SOURCE_BYTES + 1)
    with monkeypatch.context() as guard:
        guard.setattr(ast, "parse", forbidden)
        with pytest.raises(ValueError, match="file_too_large"):
            if operation is read_source:
                operation(path)
            else:
                operation(path, module_name="large")


def test_nonregular_source_is_refused_without_blocking_and_aliases_still_work(tmp_path):
    fifo = tmp_path / "pipe.py"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular_file_required"):
        read_source(fifo)
    path = tmp_path / "source.py"
    path.write_bytes(b"def predict(x: int): return x\n")
    alias = tmp_path / "alias.py"
    alias.symlink_to(path)
    assert read_source(alias) == path.read_bytes()
    assert inspect_file(alias, module_name="source").capability_ir.capabilities


@pytest.mark.parametrize("kind", ["bytes", "unicode"])
def test_inmemory_source_limit_precedes_parser(kind, monkeypatch):
    source = (
        b"#" * (MAX_SOURCE_BYTES + 1)
        if kind == "bytes"
        else "é" * (MAX_SOURCE_BYTES // 2 + 1)
    )
    with monkeypatch.context() as guard:
        guard.setattr(ast, "parse", forbidden)
        with pytest.raises(ValueError, match="source_byte_limit"):
            analyzer.inspect_source(source, module_name="large")


@pytest.mark.parametrize("kind", ["nodes", "depth"])
def test_broad_and_deep_asts_are_refused_before_recursive_analysis(kind, monkeypatch):
    source = "x=1\n" * 26000 if kind == "nodes" else "x=" + "+".join(["1"] * 200)
    monkeypatch.setattr(analyzer, "_Analyzer", forbidden)
    with pytest.raises(ValueError, match="source_structure_limit"):
        analyzer.inspect_source(source, module_name="large")


@pytest.mark.parametrize("operation", [code_cells, inspect_notebook_bytes, "exporter"])
@pytest.mark.parametrize("kind", ["nodes", "depth", "bytes"])
def test_notebook_budget_precedes_json_decoder(operation, kind, monkeypatch):
    if kind == "nodes":
        raw = b'{"metadata":[' + b"0," * 100_000 + b'0],"cells":[],"nbformat":4}'
    elif kind == "depth":
        raw = b'{"metadata":' + b"[" * 65 + b"0" + b"]" * 65 + b"}"
    else:
        raw = b" " * (MAX_SOURCE_BYTES + 1)
    exporter = NotebookTransformr() if operation == "exporter" else None
    monkeypatch.setattr(json, "loads", forbidden)
    with pytest.raises(ValueError, match="json_.*limit"):
        if operation == "exporter":
            exporter.convert_notebook(io.BytesIO(raw))
        elif operation is code_cells:
            operation(raw)
        else:
            operation(raw, module_name="notebook")


def test_json_budget_counts_keys_scalars_and_containers_but_not_string_punctuation():
    value = {"clé": [None, True, 3, 1.5, 'escaped \\" quotes \\ [] {},:']}
    raw = json.dumps(value, ensure_ascii=False).encode()
    assert (
        json.loads(preflight_json(raw, max_bytes=1000, max_nodes=8, max_depth=2))
        == value
    )
    with pytest.raises(ValueError, match="structure_limit"):
        preflight_json(raw, max_bytes=1000, max_nodes=7, max_depth=2)
    for raw in [b"}", b"]", b"[}"]:
        with pytest.raises(ValueError):
            json.loads(preflight_json(raw, max_bytes=100, max_nodes=10, max_depth=2))


def test_notebook_with_large_output_string_is_kept():
    raw = json.dumps(
        {"nbformat": 4, "cells": [], "metadata": {"output": "x" * (2 * 1024 * 1024)}}
    ).encode()
    assert code_cells(raw).source == ""


@pytest.mark.parametrize("command", ["inspect", "rest", "mcp", "execute"])
@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
def test_cli_rejects_large_source_before_outputs_or_worker(
    tmp_path, capsys, monkeypatch, command, suffix
):
    from apizr.cli import main
    from apizr.cli.commands import execute

    path = tmp_path / ("oversized" + suffix)
    with path.open("wb") as file:
        file.truncate(MAX_SOURCE_BYTES + 1)
    output = tmp_path / "bundle"
    if command == "execute":
        policy = tmp_path / "policy.json"
        arguments = tmp_path / "arguments.json"
        policy.write_text("{}")
        arguments.write_text("{}")
        monkeypatch.setattr(execute, "execute", forbidden)
        args = [
            "execute",
            str(path),
            "predict",
            "--arguments",
            str(arguments),
            "--policy",
            str(policy),
        ]
    elif command == "inspect":
        args = ["inspect", str(path)]
    else:
        args = ["generate", command, str(path), "--output-dir", str(output)]
    assert main(args) == (1 if command == "execute" else 2)
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert not output.exists()


def test_notebook_path_is_bounded_before_the_exporter(tmp_path, monkeypatch):
    path = tmp_path / "oversized.ipynb"
    with path.open("wb") as file:
        file.truncate(MAX_SOURCE_BYTES + 1)
    exporter = NotebookTransformr()
    monkeypatch.setattr(exporter.exporter, "from_file", forbidden)
    with pytest.raises(ValueError, match="file_too_large"):
        exporter.convert_notebook(path)


def test_source_kind_and_encoded_notebook_size_are_checked(tmp_path):
    with pytest.raises(ValueError, match="Source supports"):
        read_source(tmp_path / "wrong.txt")
    with pytest.raises(ValueError, match="json_byte_limit"):
        preflight_json('"éé"', max_bytes=5, max_nodes=10, max_depth=2)


@pytest.mark.parametrize("suffix", [".py", ".ipynb"])
def test_source_alias_loop_has_controlled_cli_failure(tmp_path, capsys, suffix):
    from apizr.cli import main

    path = tmp_path / ("loop" + suffix)
    path.symlink_to(path)
    assert main(["inspect", str(path)]) == 2
    assert "Traceback" not in capsys.readouterr().err
    if suffix == ".ipynb":
        with pytest.raises((ValueError, OSError)):
            NotebookTransformr().convert_notebook(path)


def test_legacy_python_resolver_failure_becomes_a_source_error(tmp_path, monkeypatch):
    def cycle(*args, **kwargs):
        raise RuntimeError("legacy symlink loop")

    with monkeypatch.context() as guard:
        guard.setattr(Path, "resolve", cycle)
        with pytest.raises(ValueError, match="source_path_invalid"):
            read_source(tmp_path / "loop.py")


def test_bounded_notebook_snapshot_preserves_filename_resources(tmp_path):
    # The historical converter accepts an explicitly selected extensionless path.
    path = tmp_path / "notebook-without-suffix"
    path.write_text(
        json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []})
    )
    converter = NotebookTransformr()
    expected_source, expected_resources = converter.exporter.from_filename(str(path))
    source, resources = converter.convert_notebook(path)
    assert source == expected_source
    assert resources["metadata"] == expected_resources["metadata"]


def test_notebook_export_uses_admitted_snapshot_after_file_changes(
    tmp_path, monkeypatch
):
    from apizr.notebooks import exporter as module

    path = tmp_path / "snapshot.ipynb"
    raw = json.dumps(
        {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}
    ).encode()
    path.write_bytes(raw)
    original_read = module.read_notebook
    converter = NotebookTransformr()
    original_export = converter.exporter.from_file

    def read_and_replace(selected):
        admitted = original_read(selected)
        path.write_bytes(b"not JSON: changed after admission")
        return admitted

    def export_snapshot(content, **kwargs):
        assert isinstance(content, io.StringIO)
        assert content.getvalue() == raw.decode()
        return original_export(content, **kwargs)

    monkeypatch.setattr(module, "read_notebook", read_and_replace)
    monkeypatch.setattr(converter.exporter, "from_file", export_snapshot)
    source, resources = converter.convert_notebook(path)
    assert isinstance(source, str)
    assert resources["metadata"]["name"] == "snapshot"


@given(
    st.recursive(
        st.none() | st.booleans() | st.integers() | st.text(),
        lambda child: (
            st.lists(child, max_size=5) | st.dictionaries(st.text(), child, max_size=5)
        ),
        max_leaves=30,
    )
)
def test_json_lexical_budget_matches_independent_decoded_node_count(value):
    def count(item):
        if isinstance(item, list):
            return 1 + sum(map(count, item))
        if isinstance(item, dict):
            return 1 + len(item) + sum(map(count, item.values()))
        return 1

    raw = json.dumps(value).encode()
    nodes = count(value)
    assert (
        json.loads(
            preflight_json(raw, max_bytes=len(raw), max_nodes=nodes, max_depth=100)
        )
        == value
    )
    with pytest.raises(ValueError, match="json_structure_limit"):
        preflight_json(raw, max_bytes=len(raw), max_nodes=nodes - 1, max_depth=100)

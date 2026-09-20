import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import nbformat
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.app import app
from apizr.main import convert
from apizr.modules.notebook_transformr.transformr.nbTransformr import NotebookTransformr

from .support import analyze, contents


@pytest.mark.parametrize(
    "source, expected",
    [
        ("def nested():\n    return " + "(" * 80 + "1" + ")" * 80, ["nested"]),
        (
            "def annotated(x: " + "list[" * 35 + "int" + "]" * 35 + "): pass",
            ["annotated"],
        ),
        (
            "def many(" + ",".join(f"arg{i}: int" for i in range(300)) + "): pass",
            ["many"],
        ),
        (
            "\n".join(f"def f{i}(): pass" for i in range(300)),
            [f"f{i}" for i in range(300)],
        ),
        (
            "if True:\n"
            + "".join("    " * i + "if True:\n" for i in range(1, 35))
            + "    " * 35
            + "def deep(): pass\n",
            ["deep"],
        ),
        (
            'def pattern(x):\n    match x:\n        case 1: return [y for y in range(5) if (z := y)]\n        case _: return "数 café \\u202e"\n',
            ["pattern"],
        ),
        (
            'text = "def fake(): class NotAClass: match case"\n# def fake():\ndef café(数): return 数\n',
            ["café"],
        ),
        (
            "def large(x: Literal["
            + ",".join(repr(str(i)) for i in range(300))
            + "]): pass",
            ["large"],
        ),
    ],
)
def test_bounded_pathological_syntax(source, expected):
    encoded = analyze(source)
    assert [f["name"] for f in json.loads(encoded)["functions"]] == expected
    assert analyze(source) == encoded


@settings(max_examples=25, deadline=None, print_blob=True)
@given(
    name=st.sampled_from(["broken", "café", "数"]),
    bad=st.sampled_from(
        [
            "def {name}(",
            "def {name}():\n  return (",
            "def {name}():\n    return 'unterminated",
            "def {name}():\n    return 1\x00",
        ]
    ),
)
def test_property_malformed_source_is_rejected_without_output_or_http_traceback(
    name, bad
):
    source = bad.format(name=name)
    with pytest.raises(SyntaxError):
        analyze(source)
    with TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "broken.py"
        path.write_text(source)
        output = root / "output"
        with pytest.raises(SyntaxError):
            convert(path, output)
        assert not contents(output)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/process_file/", files={"file": ("broken.py", source)}
    )
    assert response.status_code == 400
    assert "Traceback" not in response.text
    assert response.headers["content-type"].startswith("application/json")


def test_parser_nesting_limit_is_predictable():
    source = "def too_deep(): return " + "(" * 250 + "1" + ")" * 250
    with pytest.raises(SyntaxError, match="too many nested parentheses"):
        analyze(source)
    response = TestClient(app).post(
        "/process_file/", files={"file": ("deep.py", source)}
    )
    assert response.status_code == 400


def notebook(cells):
    return nbformat.v4.new_notebook(cells=cells)


def test_notebook_execution_state_is_not_source_of_truth(tmp_path):
    plain = notebook(
        [
            nbformat.v4.new_markdown_cell("# Description"),
            nbformat.v4.new_code_cell(
                "import math\ndef café(x: int = 1):\n    return x + 1\n"
            ),
            nbformat.v4.new_code_cell("def second():\n    return café()\n"),
        ]
    )
    state = nbformat.from_dict(json.loads(nbformat.writes(plain)))
    state.cells[1].execution_count = 99
    state.cells[1].metadata = {"tags": ["arbitrary"], "custom": "ignored state"}
    state.cells[1].outputs = [
        nbformat.v4.new_output(
            "stream",
            name="stdout",
            text='raise RuntimeError("output must not run")\ndef phantom(): pass',
        )
    ]
    state.metadata = {"custom": "state"}
    outputs = []
    for index, doc in enumerate([plain, state]):
        directory = tmp_path / str(index)
        directory.mkdir()
        path = directory / "notebook.ipynb"
        nbformat.write(doc, path)
        convert(path, directory / "output")
        outputs.append(contents(directory / "output"))
    assert outputs[0] == outputs[1]
    assert b"phantom" not in outputs[0]["notebook.py"]
    assert b"# In[" not in outputs[0]["notebook.py"]


@pytest.mark.parametrize(
    "cells",
    [
        [nbformat.v4.new_markdown_cell("# Markdown only")],
        [nbformat.v4.new_code_cell("")],
    ],
)
def test_notebook_without_functions_has_actionable_api_error(tmp_path, cells):
    path = tmp_path / "empty.ipynb"
    nbformat.write(notebook(cells), path)
    with pytest.raises(ValueError, match="No functions selected"):
        convert(path, tmp_path / "output")


def test_notebook_split_function_body_is_dedented_by_ipython(tmp_path):
    cells = [
        nbformat.v4.new_code_cell("def across(value: int):"),
        nbformat.v4.new_code_cell("    return value + 1"),
    ]
    path = tmp_path / "split.ipynb"
    nbformat.write(notebook(cells), path)
    with pytest.raises(IndentationError):
        convert(path, tmp_path / "output")
    assert not contents(tmp_path / "output")


def test_notebook_multiline_expression_can_span_cells_and_large_cell_is_bounded(
    tmp_path,
):
    cells = [
        nbformat.v4.new_code_cell("values = ("),
        nbformat.v4.new_code_cell("1, 2)\ndef value(): return values\n"),
        nbformat.v4.new_code_cell("# padding\n" * 10000),
    ]
    path = tmp_path / "split.ipynb"
    nbformat.write(notebook(cells), path)
    convert(path, tmp_path / "output")
    metadata = json.loads((tmp_path / "output/split.json").read_text())
    assert [f["name"] for f in metadata["functions"]] == ["value"]


@pytest.mark.parametrize(
    "code",
    [
        "%time 1 + 1",
        "%%time\n1 + 1",
        "!echo should_not_run",
        "files = !ls",
        'get_ipython().run_line_magic("time", "1")',
    ],
)
def test_ipython_transforms_are_rejected_not_executed(code):
    content = nbformat.writes(notebook([nbformat.v4.new_code_cell(code)]))
    with pytest.raises(ValueError, match="magics and shell commands"):
        NotebookTransformr().convert_notebook(io.StringIO(content))


@pytest.mark.parametrize(
    "payload",
    [
        "[",
        "[]",
        "null",
        '{"nbformat":4,"nbformat_minor":5,"metadata":{},"cells":[{"cell_type":"code","source":1}]}',
        '{"nbformat":99,"nbformat_minor":0,"metadata":{},"cells":[]}',
    ],
)
def test_invalid_notebook_structure_is_client_error(payload):
    client = TestClient(app, raise_server_exceptions=False)
    for endpoint in ["/process_file/", "/notebook/convert_notebook"]:
        response = client.post(endpoint, files={"file": ("invalid.ipynb", payload)})
        assert response.status_code == 400, response.text
        assert "Traceback" not in response.text


def test_unsupported_annotation_operator_is_client_error():
    source = "def operation(x: int + str): return x\n"
    client = TestClient(app, raise_server_exceptions=False)
    for endpoint in ["/process_file/", "/code/analyze_file/"]:
        response = client.post(endpoint, files={"file": ("operation.py", source)})
        assert response.status_code == 400
        assert "Unsupported binary operation" in response.json()["detail"]


@pytest.mark.parametrize("binary", [False, True], ids=["text-stream", "binary-stream"])
def test_notebook_stream_inputs_remain_supported(binary):
    document = nbformat.writes(
        notebook([nbformat.v4.new_code_cell("def value(): return 1\n")])
    )
    stream = io.BytesIO(document.encode()) if binary else io.StringIO(document)
    source, _ = NotebookTransformr().convert_notebook(stream)
    assert [f["name"] for f in json.loads(analyze(source))["functions"]] == ["value"]

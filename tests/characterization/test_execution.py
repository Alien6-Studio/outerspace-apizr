import json
import os
import socket
from pathlib import Path
from tempfile import TemporaryDirectory

import nbformat
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.main import convert

from .support import analyze, contents, runtime


@pytest.mark.parametrize("notebook", [False, True], ids=["script", "notebook"])
@pytest.mark.parametrize("action", ["file", "environment", "network", "raise"])
def test_hostile_source_only_executes_across_trusted_runtime_boundary(
    tmp_path, monkeypatch, notebook, action
):
    marker = tmp_path / "executed"
    monkeypatch.delenv("APIZR_CHARACTERIZATION_EXECUTED", raising=False)
    calls = []

    def record_network(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("controlled network boundary")

    monkeypatch.setattr(socket, "create_connection", record_network)
    monkeypatch.setattr(socket.socket, "connect", record_network)
    actions = {
        "file": f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        "environment": 'import os\nos.environ["APIZR_CHARACTERIZATION_EXECUTED"] = "yes"\n',
        "network": 'import socket\nsocket.create_connection(("invalid.example", 443))\n',
        "raise": 'raise RuntimeError("controlled top-level exception")\n',
    }
    code = actions[action] + "def value(): return 1\n"
    source = tmp_path / ("contract_source.ipynb" if notebook else "contract_source.py")
    if notebook:
        nbformat.write(
            nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code)]), source
        )
    else:
        source.write_text(code)
    original = source.read_bytes()
    analyze(code)
    convert(source, tmp_path / "output")
    assert source.read_bytes() == original
    assert not marker.exists()
    assert "APIZR_CHARACTERIZATION_EXECUTED" not in os.environ
    assert not calls
    if action in {"network", "raise"}:
        with (
            pytest.raises(RuntimeError, match="controlled"),
            runtime(tmp_path / "output"),
        ):
            pass
    else:
        with runtime(tmp_path / "output") as client:
            assert client.post("/value").json() == 1
    assert marker.exists() == (action == "file")
    assert os.environ.get("APIZR_CHARACTERIZATION_EXECUTED") == (
        "yes" if action == "environment" else None
    )
    assert bool(calls) == (action == "network")
    monkeypatch.delenv("APIZR_CHARACTERIZATION_EXECUTED", raising=False)


def test_decorator_expression_and_wrapper_run_only_at_import(tmp_path, monkeypatch):
    marker = tmp_path / "decorated"
    source = f'''from pathlib import Path
from functools import wraps
def decorate(label):
    Path({str(marker)!r}).touch()
    def apply(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return label + str(fn(*args, **kwargs))
        return wrapper
    return apply
@decorate("outer:")
@decorate("inner:")
def value(x: int):
    """ordinary docstring"""
    return x
'''
    # Ignore the factory: discovery does not execute decorator expressions.
    metadata = json.loads(analyze(source, functions_to_analyze="value"))
    plain = json.loads(
        analyze("def value(x: int): return x\n", functions_to_analyze="value")
    )
    assert metadata["functions"] == plain["functions"]
    path = tmp_path / "contract_source.py"
    path.write_text(source)
    config = tmp_path / "config.yaml"
    config.write_text("code_analyzr:\n  functions_to_analyze: value\n")
    convert(path, tmp_path / "output", configuration=config)
    assert not marker.exists()
    with runtime(tmp_path / "output") as client:
        assert marker.exists()
        assert client.post("/value", json={"x": 2}).json() == "outer:inner:2"


@settings(max_examples=15, deadline=None, print_blob=True)
@given(
    value=st.integers(-100, 100), as_notebook=st.booleans(), asynchronous=st.booleans()
)
def test_property_artifacts_are_identical_across_output_locations(
    value, as_notebook, asynchronous
):
    with TemporaryDirectory() as directory, pytest.MonkeyPatch.context() as patch:
        root = Path(directory)

        def deny(*args, **kwargs):
            pytest.fail("generation attempted network access")

        patch.setattr(socket.socket, "connect", deny)
        patch.setattr(socket, "create_connection", deny)
        source = root / ("unicode_source.ipynb" if as_notebook else "unicode_source.py")
        code = f'"""def fake(): match case"""\nraise RuntimeError("not executed")\n{"async " if asynchronous else ""}def café(数: int = {value}):\n    return 数\n'
        if as_notebook:
            nbformat.write(
                nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code)]),
                source,
            )
        else:
            source.write_text(code)
        before = source.read_bytes()
        convert(source, root / "first")
        convert(source, root / "second")
        first = contents(root / "first")
        assert first == contents(root / "second")
        assert all(str(root).encode() not in content for content in first.values())
        assert source.read_bytes() == before


def test_signature_changing_decorator_loses_runtime_validation(tmp_path):
    source = """def replace(fn):
    def wrapper(*args, **kwargs):
        return kwargs["value"]
    return wrapper
@replace
def echo(value: int):
    return value
"""
    config = tmp_path / "config.yaml"
    config.write_text("code_analyzr:\n  functions_to_analyze: echo\n")
    path = tmp_path / "contract_source.py"
    path.write_text(source)
    convert(path, tmp_path / "output", configuration=config)
    assert (
        json.loads(analyze(source))["functions"][1]["args"][0]["annotation"]["type"]
        == "int"
    )
    with runtime(tmp_path / "output") as client:
        assert (
            client.post("/echo", json={"value": "not an integer"}).json()
            == "not an integer"
        )

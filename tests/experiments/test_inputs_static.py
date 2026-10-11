"""Conservative literal-loader authority and bounded deterministic discovery."""

import json
import os
import subprocess
import sys

import pytest

from apizr.experiments import (
    EvidenceOrigin,
    InputDeclaration,
    InputResult,
    discover_inputs,
    inputs,
    parse_input_declaration,
    select_inputs,
)


def scan(source):
    return discover_inputs(source, source_reference="train.py")


@pytest.mark.parametrize(
    "statement,call,hint",
    [
        ("import pandas", "pandas.read_csv", "csv"),
        ("import pandas as pd", "pd.read_parquet", "parquet"),
        ("from pandas import read_csv", "read_csv", "csv"),
        ("from pandas import read_parquet as read", "read", "parquet"),
        ("import numpy as np", "np.load", "numpy"),
        ("from numpy import load as read", "read", "numpy"),
        ("import joblib", "joblib.load", "joblib"),
        ("from joblib import load", "load", "joblib"),
    ],
)
def test_recognized_loaders(statement, call, hint):
    result = scan(f'{statement}\n{call}("data/train.csv")')
    (artifact,) = result.artifacts
    assert artifact.name == artifact.reference == "data/train.csv"
    assert artifact.origin is EvidenceOrigin.STATIC
    assert artifact.content_origin is EvidenceOrigin.UNKNOWN
    assert artifact.digest is artifact.size is None
    assert artifact.format_hint == hint
    assert result.diagnostics == ()


@pytest.mark.parametrize(
    "expression",
    [
        "DATA_PATH",
        'config["path"]',
        'f"data/{name}.csv"',
        'Path("data") / filename',
        "*paths",
        "42",
        'b"data.csv"',
        "None",
        'path="data.csv"',
        "",
    ],
)
def test_dynamic_stays_dynamic(expression):
    result = scan(
        f'import pandas as pd\nDATA_PATH="data.csv"\npd.read_csv({expression})'
    )
    assert result.artifacts == ()
    (diagnostic,) = result.diagnostics
    assert diagnostic.code == "dynamic_input_reference"
    assert (
        diagnostic.source,
        diagnostic.line,
        diagnostic.column,
        diagnostic.loader,
    ) == ("train.py", 3, 0, "pandas.read_csv")


@pytest.mark.parametrize(
    "source",
    [
        'pd.read_csv("x")',
        'import pandas as pd\npd = fake\npd.read_csv("x")',
        'import pandas as pd\ndel pd\npd.read_csv("x")',
        'if condition:\n import pandas as pd\npd.read_csv("x")',
        'from pandas import *\nread_csv("x")',
        'import pandas as pd\nfrom unknown import *\npd.read_csv("x")',
        'pd=__import__("pandas")\npd.read_csv("x")',
        'import pandas as pd\ndef train(pd):\n return pd.read_csv("x")',
        'import pandas as pd\ndef train():\n pd.read_csv("x")\n pd=other',
        'import pandas as pd\ndef train():\n global pd\n pd.read_csv("x")',
        'import pandas as pd\ndef outer():\n def inner():\n  nonlocal pd\n  pd.read_csv("x")',
        'import pandas as pd\n(lambda pd: pd.read_csv("x"))(other)',
        'import pandas as pd\n[pd.read_csv("x") for pd in readers]',
        'import pandas as pd\npd.read_csv = fake\npd.read_csv("x")',
        'import pandas as pd\npd.io.read_csv = fake\npd.read_csv("x")',
        'import pandas as pd\nfor pd in readers:\n pd.read_csv("x")',
        'import pandas as pd\ntry:\n pass\nexcept Exception as pd:\n pd.read_csv("x")',
        'import pandas as pd\nmatch obj:\n case pd:\n  pd.read_csv("x")',
        'import pandas as pd\nmatch obj:\n case [*pd]:\n  pd.read_csv("x")',
        'import pandas as pd\nmatch obj:\n case {**pd}:\n  pd.read_csv("x")',
        'from .pandas import read_csv\nread_csv("x")',
        'import pandas as pd\npd.read_sql("query")',
        'import pandas.submodule\npandas.read_csv("x")',
        'import pandas as pd\nimport pandas as pd\npd.read_csv("x")',
        'pd.read_csv("x")\nimport pandas as pd',
        'import other\nother.read_csv("x")',
        'from pandas import other\nother("x")',
        'obj.factory.read_csv("x")',
        'open("x")',
    ],
)
def test_no_authority_by_spelling(source):
    assert scan(source).artifacts == ()


@pytest.mark.parametrize(
    "source",
    [
        'import pandas as pd\ndef train():\n return pd.read_csv("x")',
        'import pandas as pd\nasync def train():\n return pd.read_csv("x")',
        'def train():\n import pandas as pd\n return pd.read_csv("x")',
        'import pandas as pd\ndef outer():\n def inner():\n  return pd.read_csv("x")',
        'import pandas as pd\nclass Trainer:\n pd=other\n def train(self):\n  return pd.read_csv("x")',
        'import pandas as pd\nclass Trainer:\n value=pd.read_csv("x")',
        'import pandas as pd\n(lambda: pd.read_csv("x"))',
        'import pandas as pd\n[pd.read_csv("x") for index in range(2)]',
        'import pandas as pd\n{pd.read_csv("x") for index in range(2)}',
        'import pandas as pd\n{index:pd.read_csv("x") for index in range(2)}',
        'import pandas as pd\n(pd.read_csv("x") for index in range(2))',
        'import pandas as pd; pd.read_csv("x")',
        'import pandas as pd\ndef train(value=pd.read_csv("x")): pass',
        'import pandas as pd\n@decorate(pd.read_csv("x"))\ndef train(): pass',
        'import pandas as pd\ndef train(value:pd.read_csv("x")): pass',
    ],
)
def test_lexical_scopes(source):
    assert len(scan(source).artifacts) == 1


def test_indirect_loader_has_no_invented_path():
    result = scan('get_loader()("data.csv")')
    assert result.artifacts == ()
    assert result.diagnostics[0].code == "unsupported_input_reference"
    assert result.diagnostics[0].loader is None


@pytest.mark.parametrize(
    "reference,code",
    [
        ("/Users/alice/private/train.csv", "nonportable_input_reference"),
        ("../train.csv", "nonportable_input_reference"),
        ("data/./train.csv", "nonportable_input_reference"),
        ("data//train.csv", "nonportable_input_reference"),
        ("C:\\train.csv", "nonportable_input_reference"),
        ("~/train.csv", "nonportable_input_reference"),
        ("data\x00.csv", "nonportable_input_reference"),
        ("data\ud800.csv", "nonportable_input_reference"),
        ("https://user:secret@host/data", "unsupported_input_reference"),
        ("file:///etc/passwd", "unsupported_input_reference"),
        ("https://host/data?secret=token", "unsupported_input_reference"),
        ("a" * 129, "input_name_required"),
        ("s3://bucket/" + "a" * 129, "input_name_required"),
        ("a" * 1025, "nonportable_input_reference"),
    ],
)
def test_rejected_literals_are_redacted(reference, code):
    result = scan(f"import pandas as pd\npd.read_csv({reference!r})")
    assert not result.artifacts
    assert result.diagnostics[0].code == code
    assert reference not in result.model_dump_json()


def test_remote_static():
    result = scan('import pandas as pd\npd.read_parquet("s3://bucket/train.parquet")')
    (artifact,) = result.artifacts
    assert artifact.uri == "s3://bucket/train.parquet" and artifact.reference is None
    assert artifact.format_hint == "parquet"
    assert artifact.digest is artifact.size is None
    assert result.diagnostics[0].code == "remote_content_unverified"


def test_duplicate_reads_and_conflicting_hints():
    result = scan('import pandas as pd\npd.read_csv("x")\npd.read_csv("x")')
    assert len(result.artifacts) == 1 and not result.diagnostics
    result = scan(
        'import pandas as pd\npd.read_csv("x")\npd.read_parquet("x")\npd.read_csv("x")'
    )
    assert len(result.artifacts) == 1
    assert result.artifacts[0].format_hint is None
    assert {item.code for item in result.diagnostics} == {"input_format_conflict"}


@pytest.mark.parametrize("source", ["def invalid(", b"\xff", "\ud800", "x\x00"])
def test_invalid_source(source):
    assert scan(source).diagnostics[0].code == "input_source_invalid"


def test_invalid_source_identity():
    result = discover_inputs("pass", source_reference="/Users/private/train.py")
    assert result.diagnostics[0].source is None
    assert "/Users" not in result.model_dump_json()


def test_bounded_source_and_tree(monkeypatch):
    assert (
        scan("#" * (inputs._MAX_SOURCE_BYTES + 1)).diagnostics[0].code
        == "input_discovery_limit"
    )
    monkeypatch.setattr(inputs, "_MAX_NODES", 3)
    assert scan("x=1").diagnostics[0].code == "input_discovery_limit"
    monkeypatch.setattr(inputs, "_MAX_NODES", 100_000)
    monkeypatch.setattr(inputs, "_MAX_DEPTH", 2)
    assert scan("x=1+2").diagnostics[0].code == "input_discovery_limit"


@pytest.mark.parametrize(
    "calls",
    [
        "\n".join(f'pd.read_csv("file{index}")' for index in range(257)),
        "\n".join("pd.read_csv(dynamic)" for _ in range(513)),
    ],
)
def test_bounded_results(calls):
    result = scan("import pandas as pd\n" + calls)
    assert not result.artifacts
    assert result.diagnostics[0].code == "input_discovery_limit"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "training",
        "=x",
        "train=",
        "train=/private/x",
        "train=../x",
        "train=file:///x",
        "train=https://host/x?q=secret",
        "x" * 1154,
        None,
        12,
    ],
)
def test_declaration_parser_redacts_invalid_values(value):
    with pytest.raises(ValueError, match="^explicit_input_invalid$"):
        parse_input_declaration(value)


@pytest.mark.parametrize(
    "value,reference,uri",
    [
        ("training=data/train.parquet", "data/train.parquet", None),
        ("training=s3://bucket/train.parquet", None, "s3://bucket/train.parquet"),
        ("training=data/a=b.csv", "data/a=b.csv", None),
    ],
)
def test_declaration_parser(value, reference, uri):
    item = parse_input_declaration(value)
    assert item == InputDeclaration(name="training", reference=reference, uri=uri)


def test_selection_preserves_declaration_and_dynamic_uncertainty():
    discovery = scan(
        'import pandas as pd\npd.read_csv("data.csv")\npd.read_csv(DATA_PATH)\npd.read_csv("other.csv")'
    )
    declarations = (
        parse_input_declaration("train=data.csv"),
        parse_input_declaration("validation=data.csv"),
    )
    result = select_inputs(discovery, declarations)
    assert [item.name for item in result.artifacts] == [
        "other.csv",
        "train",
        "validation",
    ]
    assert all(item.origin is EvidenceOrigin.DECLARED for item in result.artifacts[1:])
    assert result.diagnostics == discovery.diagnostics
    assert select_inputs(discovery) == discovery


def test_duplicate_declaration_names_rejected():
    declarations = (parse_input_declaration("x=a"), parse_input_declaration("x=b"))
    with pytest.raises(ValueError, match="explicit_input_invalid"):
        select_inputs(InputResult(), declarations)
    with pytest.raises(ValueError, match="explicit_input_invalid"):
        select_inputs(InputResult(), (declarations[0],) * 257)
    discovery = scan('import pandas as pd\npd.read_csv("x")')
    with pytest.raises(ValueError, match="explicit_input_invalid"):
        select_inputs(discovery, (declarations[0],))


def test_discovery_hashseed_determinism(tmp_path):
    source = 'import pandas as pd\npd.read_csv("b.csv")\npd.read_csv("a.csv")\npd.read_csv(DATA_PATH)'
    code = f'from apizr.experiments import discover_inputs; print(discover_inputs({source!r}, source_reference="train.py").model_dump_json())'
    outputs = [
        subprocess.check_output(
            [sys.executable, "-c", code],
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
            cwd=tmp_path,
            text=True,
        )
        for seed in (1, 71)
    ]
    assert outputs[0] == outputs[1] == scan(source).model_dump_json() + "\n"
    assert [item["name"] for item in json.loads(outputs[0])["artifacts"]] == [
        "a.csv",
        "b.csv",
    ]


@pytest.mark.parametrize(
    "source",
    [
        'import pandas as pd\n(lambda pd: lambda: pd.read_csv("x"))(other)',
        'import pandas as pd\n[(lambda: pd.read_csv("x")) for pd in readers]',
    ],
)
def test_nested_closure_does_not_recover_shadowed_authority(source):
    assert scan(source).artifacts == ()


@pytest.mark.parametrize(
    "source",
    [
        'import pandas as pd\nitems[0].attr = 1\npd.read_csv("x")',
        'import pandas as pd\ntry:\n pass\nexcept Exception:\n pd.read_csv("x")',
        'import pandas as pd\nmatch obj:\n case _:\n  pd.read_csv("x")',
        'import pandas as pd\nmatch obj:\n case {"x": x}:\n  pd.read_csv("x")',
    ],
)
def test_nonbinding_syntax_retains_authority(source):
    assert len(scan(source).artifacts) == 1


@pytest.mark.parametrize(
    "source",
    [
        'class Outer:\n import pandas as pd\n class Inner:\n  value = pd.read_csv("x")',
        'class Outer:\n import pandas as pd\n values = [pd.read_csv("x") for i in range(2)]',
        'import pandas as pd\ndef replace():\n global pd\n pd = other\nreplace()\npd.read_csv("x")',
        'import pandas as pd\ndef replace():\n pd.read_csv = other\nreplace()\npd.read_csv("x")',
        'def outer():\n import pandas as pd\n def replace():\n  nonlocal pd\n  pd=other\n replace()\n return pd.read_csv("x")',
    ],
)
def test_nested_scopes_do_not_grant_false_authority(source):
    assert scan(source).artifacts == ()


def test_generic_scope_is_not_confused_with_module_import(monkeypatch):
    # Construct a generic AST shape on every supported interpreter, including 3.11.
    # Native type-parameter parsing is separately covered where syntax exists.
    import ast

    source = 'import pandas as pd\ndef train():\n return pd.read_csv("x")'
    tree = ast.parse(source)
    tree.body[1].type_params = [ast.Name(id="pd", ctx=ast.Store())]
    monkeypatch.setattr(inputs.ast, "parse", lambda value: tree)
    assert scan(source).artifacts == ()


def test_native_generic_scope_when_syntax_available():
    result = scan('import pandas as pd\ndef train[pd]():\n return pd.read_csv("x")')
    assert result.artifacts == ()
    assert all(item.code == "input_source_invalid" for item in result.diagnostics)

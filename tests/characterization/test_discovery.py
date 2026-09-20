import json
import socket
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.modules.code_analyzr.analyzr.astAnalyzr import AstAnalyzr
from apizr.modules.code_analyzr.configuration import CodeAnalyzrConfiguration

from .support import analyze, corpus


@pytest.mark.parametrize("case", corpus("discovery.json"), ids=lambda case: case["id"])
def test_discovery_corpus(case):
    assert case["classification"] in {
        "SUPPORTED",
        "EXPLICITLY REJECTED",
        "LEGACY OBSERVED",
        "FUTURE CANDIDATE",
    }
    if case["error"]:
        with pytest.raises(ValueError, match=case["error"]):
            analyze(case["source"])
    else:
        result = analyze(case["source"])
        assert result == analyze(case["source"])
        assert [f["name"] for f in json.loads(result)["functions"]] == case["names"]


# Finite valid grammar, not arbitrary text filtered through broad assumptions.
identifiers = st.sampled_from(
    ["first", "café", "数", "_private", "model_dump", "function_" + "x" * 200]
)


@settings(max_examples=60, deadline=None, print_blob=True)
@given(
    names=st.lists(identifiers, min_size=1, max_size=5, unique=True),
    asynchronous=st.booleans(),
    default=st.sampled_from(["", " = None", " = 3"]),
    positional=st.booleans(),
    keyword=st.booleans(),
)
def test_property_discovery_is_stable_under_irrelevant_text(
    names, asynchronous, default, positional, keyword
):
    args = (
        "value: int"
        + default
        + (", /" if positional else "")
        + (", *, flag: bool = False" if keyword else "")
    )
    bodies = [
        f"{'async ' if asynchronous else ''}def {name}({args}) -> int:\n    return value\n"
        for name in names
    ]
    plain = "\n".join(bodies)
    decorated = "# class Fake: def phantom():\n\n" + "\n\n".join(
        body.replace(
            "    return",
            '    """ordinary documentation: def hidden():"""\n    # match case\n    return',
        )
        for body in bodies
    )
    first = analyze(plain)
    assert first == analyze(decorated)
    functions = json.loads(first)["functions"]
    assert [f["name"] for f in functions] == names  # source order is contractual
    assert functions[0]["args"][0].get("has_default", False) == bool(default)
    assert functions[0].get("is_async", False) == asynchronous
    assert functions[0]["args"][0].get("kind", "positional_or_keyword") == (
        "positional_only" if positional else "positional_or_keyword"
    )


@settings(max_examples=35, deadline=None, print_blob=True)
@given(
    selected=st.sets(st.sampled_from(["keep", "ignore", "outer"])),
    ignored=st.sets(st.sampled_from(["keep", "ignore", "outer"])),
)
def test_property_selection_never_traverses_nested_or_class_bodies(selected, ignored):
    source = "def keep(): pass\ndef ignore(): pass\ndef outer():\n    def nested(*args): pass\n    return nested\nclass C:\n    def method(*args): pass\n"
    result = json.loads(
        analyze(
            source,
            functions_to_analyze=",".join(sorted(selected)),
            ignore=",".join(sorted(ignored)),
        )
    )
    expected = [
        name
        for name in ["keep", "ignore", "outer"]
        if (not selected or name in selected) and name not in ignored
    ]
    assert [f["name"] for f in result["functions"]] == expected


@settings(max_examples=25, deadline=None, print_blob=True)
@given(value=st.integers(-1000, 1000))
def test_property_analysis_is_pure_and_state_is_reset(value):
    with TemporaryDirectory() as directory, pytest.MonkeyPatch.context() as patch:
        marker = Path(directory) / "executed"
        source = f'from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError("must not run")\ndef value(): return {value}\n'
        path = Path(directory) / "source.py"
        path.write_text(source)

        def deny(*args, **kwargs):
            pytest.fail("analysis attempted a network connection")

        patch.setattr(socket.socket, "connect", deny)
        patch.setattr(socket, "create_connection", deny)
        analyzer = AstAnalyzr(CodeAnalyzrConfiguration(), source)
        first = analyzer.get_analyse()
        assert json.loads(first)["functions"][0]["name"] == "value"
        assert first == analyzer.get_analyse()
        analyzer.code_str = "def replacement(): pass\n"
        assert [f["name"] for f in json.loads(analyzer.get_analyse())["functions"]] == [
            "replacement"
        ]
        analyzer.code_str = "def broken("
        with pytest.raises(SyntaxError):
            analyzer.get_analyse()
        analyzer.code_str = source
        assert analyzer.get_analyse() == first
        assert not marker.exists()
        assert path.read_text() == source

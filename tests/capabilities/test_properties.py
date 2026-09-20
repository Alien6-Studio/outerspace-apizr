import os
import socket
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.capabilities import canonical_bytes, inspect_file, inspect_source
from apizr.capabilities.model import DiagnosticCode

IDENTIFIERS = st.from_regex(r"cap_[a-z]{1,12}", fullmatch=True)


@settings(max_examples=35, deadline=None, print_blob=True)
@given(IDENTIFIERS, st.integers(), st.text(alphabet=" abcdefé数", max_size=40))
def test_determinism_and_location_independence(name, number, comment):
    source = f"# {comment}\ndef {name}(value: int = {number}) -> int:\n return value\n".encode()
    with (
        TemporaryDirectory(prefix="cap-first-") as first,
        TemporaryDirectory(prefix="cap-second-") as second,
    ):
        a = Path(first) / "one.py"
        b = Path(second) / "entirely-unrelated.py"
        a.write_bytes(source)
        b.write_bytes(source)
        expected = canonical_bytes(inspect_source(source, module_name="logical"))
        assert (
            canonical_bytes(inspect_source(source, module_name="logical")) == expected
        )
        assert canonical_bytes(inspect_file(a, module_name="logical")) == expected
        assert canonical_bytes(inspect_file(b, module_name="logical")) == expected


@settings(max_examples=35, deadline=None, print_blob=True)
@given(IDENTIFIERS, st.integers(min_value=1, max_value=8))
def test_identity_survives_formatting_but_exact_source_digest_changes(name, padding):
    a = inspect_source(f"def {name}(x:int): return x\n", module_name="logical")
    b = inspect_source(
        "\n" * padding + f"# comment\ndef {name}( x: int ):\n    return x\n",
        module_name="logical",
    )
    assert a.capabilities[0].id == b.capabilities[0].id
    assert a.source.digest != b.source.digest


@settings(max_examples=30, deadline=None, print_blob=True)
@given(st.lists(IDENTIFIERS, min_size=1, max_size=10))
def test_unique_ids_and_deterministic_ambiguity(names):
    source = "".join(f"def {name}(): pass\n" for name in names)
    a = inspect_source(source, module_name="duplicates")
    b = inspect_source(source, module_name="duplicates")
    ids = [c.id for c in a.capabilities]
    assert len(ids) == len(set(ids))
    assert {c.name for c in a.capabilities} == {
        name for name in names if names.count(name) == 1
    }
    assert {
        d.source.symbol for d in a.diagnostics if d.code == DiagnosticCode.DUPLICATE
    } == {name for name in names if names.count(name) > 1}
    assert canonical_bytes(a) == canonical_bytes(b)


@settings(max_examples=25, deadline=None, print_blob=True)
@given(
    st.sampled_from(["top_level", "default", "annotation", "decorator", "body"]),
    IDENTIFIERS,
)
def test_hostile_source_never_executes_any_phase(phase, name):
    with TemporaryDirectory(prefix="cap-hostile-") as directory:
        marker = Path(directory) / "should-not-exist"
        payload = f"(__import__('pathlib').Path({str(marker)!r}).write_text('executed'), __import__('os').environ.__setitem__('APIZR_IR_EXECUTED', 'yes'), __import__('socket').create_connection(('127.0.0.1', 9)))"
        forms = {
            "top_level": f"{payload}\nraise RuntimeError('top level executed')\ndef {name}(): pass\n",
            "default": f"def {name}(x={payload}): pass\n",
            "annotation": f"def {name}(x: {payload}) -> {payload}: pass\n",
            "decorator": f"@{payload}\ndef {name}(): pass\n",
            "body": f"def {name}():\n return {payload}\n",
        }
        before = dict(os.environ)
        with (
            patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network during analysis"),
            ),
            patch(
                "builtins.open",
                side_effect=AssertionError("file access during in-memory inspection"),
            ),
        ):
            document = inspect_source(forms[phase], module_name="hostile")
        assert document.capabilities[0].name == name
        assert not marker.exists()
        assert dict(os.environ) == before


def test_importing_core_does_not_load_generation_frameworks():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            """
import sys
from apizr.capabilities import inspect_source
inspect_source('def f(): pass', module_name='isolated')
for forbidden in ('fastapi', 'starlette', 'jinja2', 'nbconvert', 'apizr.main', 'apizr.modules'):
    assert forbidden not in sys.modules, forbidden
""",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

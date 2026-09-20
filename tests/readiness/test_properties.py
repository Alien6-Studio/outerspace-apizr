import builtins
import os
import socket
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.cli import main
from apizr.inspection import inspect_file, inspect_source, json_bytes
from apizr.readiness.model import Code, State

NAMES = st.from_regex(r"cap_[a-z]{1,10}", fullmatch=True)


@settings(max_examples=35, deadline=None, print_blob=True)
@given(
    st.lists(
        st.sampled_from(["declaration", "rebind", "delete"]), min_size=1, max_size=8
    )
)
def test_binding_sequence_is_deterministic_and_never_selects_ambiguous_definitions(
    events,
):
    pieces = {
        "declaration": "def f(x: int): return x\n",
        "rebind": "f = replacement\n",
        "delete": "del f\n",
    }
    source = "".join(pieces[event] for event in events)
    first = inspect_source(source, module_name="bindings")
    second = inspect_source(source, module_name="bindings")
    assert json_bytes(first) == json_bytes(second)
    if events.count("declaration") > 1:
        assert first.readiness.assessments[0].state == State.AMBIGUOUS
        assert not first.capability_ir.capabilities
    elif (
        events.count("declaration") == 1
        and events.index("declaration") < len(events) - 1
    ):
        value = first.readiness.assessments[0]
        assert value.dimensions.binding.state == State.CONDITIONAL
        assert Code.REBOUND in {r.code for r in value.dimensions.binding.reasons}
        assert not value.can_generate_interface


@settings(max_examples=30, deadline=None, print_blob=True)
@given(NAMES, st.integers(), st.booleans())
def test_reports_and_identity_do_not_depend_on_file_location(name, default, rebound):
    source = f"def {name}(x: int = {default}) -> int: return x\n"
    if rebound:
        source += f"{name} = replacement\n"
    with TemporaryDirectory() as first, TemporaryDirectory() as second:
        a = Path(first) / "first.py"
        b = Path(second) / "different.py"
        a.write_text(source)
        b.write_text(source)
        assert json_bytes(inspect_file(a, module_name="stable")) == json_bytes(
            inspect_file(b, module_name="stable")
        )


@settings(max_examples=30, deadline=None, print_blob=True)
@given(
    st.sampled_from(["decorator", "default", "annotation", "assignment", "earlier"]),
    NAMES,
)
def test_hostile_source_and_cli_do_not_execute_import_connect_or_spawn(phase, name):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        marker = root / "execution-marker"
        path = root / (name + ".py")
        payload = f"(__import__('pathlib').Path({str(marker)!r}).touch(), __import__('os').environ.__setitem__('APIZR_READINESS_EXECUTED','yes'), __import__('socket').create_connection(('127.0.0.1',9)), __import__('subprocess').run(['false']))"
        forms = {
            "decorator": f"@{payload}\ndef f(): pass",
            "default": f"def f(x={payload}): pass",
            "annotation": f"def f(x: {payload}): pass",
            "assignment": f"def f(): pass\nf = {payload}",
            "earlier": f'{payload}\nraise RuntimeError("executed source")\ndef f(): pass',
        }
        source = forms[phase]
        path.write_text(source)
        original_import = builtins.__import__
        before = dict(os.environ)

        def guarded_import(module, *args, **kwargs):
            assert module != name, "imported target module"
            return original_import(module, *args, **kwargs)

        def forbidden(*args, **kwargs):
            raise AssertionError("inspection attempted network or subprocess")

        with (
            patch.object(builtins, "__import__", guarded_import),
            patch.object(socket.socket, "connect", forbidden),
            patch.object(socket, "create_connection", forbidden),
            patch.object(subprocess, "Popen", forbidden),
            patch.object(os, "system", forbidden),
        ):
            result = inspect_source(source, module_name=name)
            assert main(["inspect", str(path), "--ir"]) == result.exit_code
        assert not marker.exists()
        assert dict(os.environ) == before

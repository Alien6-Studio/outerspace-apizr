import io
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.capabilities.model import Digest
from apizr.execution import worker
from apizr.execution.model import Request
from apizr.execution.policy import PolicyRefused
from apizr.execution.protocol import decode, encode, frame
from apizr.execution.serialization import digest
from apizr.interfaces.runtime import BindingError, IntegrityError

from .helpers import request_root


@pytest.mark.parametrize(
    "source,payload,status,value",
    [
        ("def f(a:int=7,/,*,b:int=2): return a+b", {}, "success", 9),
        ("async def f(a:int): return a", {"a": 3}, "success", 3),
        ('def f(): raise RuntimeError("secret")', {}, "execution_failed", None),
        ("def f(): return {1,2}", {}, "result_invalid", None),
        ('def f(): return "x"*200', {}, "output_limit", None),
        ("def f(a:int): return a", {"a": None}, "invalid_input", None),
    ],
)
def test_worker_shared_contract(tmp_path, source, payload, status, value):
    with request_root(
        tmp_path, source, payload, limits={"max_output_bytes": 128}
    ) as request:
        result = worker.handle(request, tmp_path)
    assert result.status == status
    assert result.value == value
    assert "secret" not in result.model_dump_json()


@pytest.mark.parametrize(
    "fault",
    ["request_digest", "plan", "missing", "policy", "integrity", "binding", "import"],
)
def test_worker_defense_before_invocation(tmp_path, monkeypatch, fault):
    with request_root(tmp_path, "def f(): return 1") as request:
        if fault == "request_digest":
            request = request.model_copy(
                update={"plan_digest": Digest.of_bytes(b"bad")}
            )
        elif fault == "plan":
            bad = request.plan.model_copy(
                update={"interface_digest": Digest.of_bytes(b"bad")}
            )
            request = Request(plan=bad, plan_digest=digest(bad), arguments={})
        elif fault == "missing":
            (tmp_path / "original").unlink()
        else:
            error = {
                "policy": PolicyRefused("unsupported_control"),
                "integrity": IntegrityError("secret"),
                "binding": BindingError("secret"),
                "import": RuntimeError("secret"),
            }[fault]

            def fail(*args):
                raise error

            monkeypatch.setattr(
                worker, "validate_plan" if fault == "policy" else "load_source", fail
            )
        result = worker.handle(request, tmp_path)
        expected = {
            "policy": "policy_refused",
            "integrity": "source_mismatch",
            "import": "execution_failed",
        }.get(fault, "binding_failed")
        assert result.status == expected
        assert result.value is None
        assert "secret" not in result.model_dump_json()


@settings(max_examples=15, deadline=None)
@given(st.binary(min_size=1, max_size=40))
def test_mutated_executable_refused_before_import(tmp_path_factory, mutation):
    root = tmp_path_factory.mktemp("mutation")
    with request_root(root, "def f(): return 1") as request:
        path = root / request.plan.executable_path
        path.write_bytes(path.read_bytes() + mutation)

        def forbidden(*args):
            pytest.fail("tampered source imported")

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(worker, "load_source", forbidden)
            assert worker.handle(request, root).status == "source_mismatch"


@pytest.mark.parametrize("replacement", [None, 3, lambda other: other, lambda x=1: x])
def test_runtime_binding_contradiction(tmp_path, monkeypatch, replacement):
    with request_root(tmp_path, "def f(x:int): return x", {"x": 1}) as request:
        monkeypatch.setattr(
            worker, "load_source", lambda *args: SimpleNamespace(f=replacement)
        )
        assert worker.handle(request, tmp_path).status == "binding_failed"


def test_worker_main_single_framed_request_and_response(tmp_path, monkeypatch):
    class Output(io.BytesIO):
        def close(self):
            pass

    output = Output()
    with request_root(tmp_path, "def f(): return 7") as request:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            worker.sys,
            "stdin",
            SimpleNamespace(
                buffer=io.BytesIO(
                    frame(encode(request.model_dump(mode="json"), 100000))
                )
            ),
        )
        monkeypatch.setattr(worker.os, "dup", lambda fd: 99)
        monkeypatch.setattr(worker.os, "dup2", lambda *args: None)
        monkeypatch.setattr(worker.os, "fdopen", lambda *args: output)
        worker.main()
        assert decode(output.getvalue(), 10000)["value"] == 7
        output.seek(0)
        output.truncate()
        worker.main()  # exhausted/truncated input is sanitized
        assert decode(output.getvalue(), 128)["status"] == "worker_failed"

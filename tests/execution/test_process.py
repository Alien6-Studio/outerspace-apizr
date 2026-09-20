import os
import sys
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.execution import execute
from apizr.execution.policy import Environment
from apizr.execution.supervisor import exchange, worker_environment

from .helpers import planned

pytestmark = pytest.mark.timeout(20)


def invoke(source, payload=None, **policy):
    runtime, raw = planned(source, **policy)
    return execute(runtime, raw, {} if payload is None else payload)


@pytest.mark.parametrize(
    ("source", "payload", "value"),
    [
        (
            "def f(a: int, /, b: int=2, *, c: int=3): return [a,b,c]",
            {"a": 1},
            [1, 2, 3],
        ),
        ("async def f(x: int): return x+1", {"x": 2}, 3),
        ("def f(x: int = None): return x", {}, None),
        ("def f(x: int | None): return x", {"x": None}, None),
        (
            "def f(x: tuple[int,str], *, y: set[int]): return [type(x).__name__,type(y).__name__]",
            {"x": [1, "a"], "y": [2]},
            ["tuple", "set"],
        ),
        ("def f() -> int: return {'not':'an int'}", {}, {"not": "an int"}),
    ],
)
def test_real_sync_async_and_shared_binding(source, payload, value):
    result = invoke(source, payload)
    assert result.status == "success" and result.value == value


def test_input_refusal_happens_without_spawning(monkeypatch):
    from apizr.execution import supervisor

    monkeypatch.setattr(
        supervisor.subprocess, "Popen", lambda *a, **kw: pytest.fail("worker started")
    )
    for payload in [{}, {"x": None}, {"x": True}, {"x": 1, "other": 3}]:
        assert invoke("def f(x: int): return x", payload).status == "invalid_input"
    assert (
        invoke(
            "def f(x: str): return x", {"x": "a" * 200}, limits={"max_input_bytes": 32}
        ).status
        == "invalid_input"
    )
    assert (
        invoke("def f(a: int=1,b: int=2,/): return b", {"b": 2}).status
        == "invalid_input"
    )


@pytest.mark.parametrize("body", ["while True: pass", "time.sleep(3600)"])
def test_noncooperative_timeout_kills_worker(tmp_path, body):
    marker = tmp_path / "pid"
    source = f"import os\nimport time\nfrom pathlib import Path\ndef f():\n    Path({str(marker)!r}).write_text(str(os.getpid()))\n    {body}\n"
    started = time.monotonic()
    result = invoke(source, limits={"wall_time_ms": 700})
    assert result.status == "timeout" and time.monotonic() - started < 5
    pid = int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.parametrize("body", ["os._exit(7)", "os.kill(os.getpid(),signal.SIGKILL)"])
def test_abnormal_exit_is_contained(body):
    assert (
        invoke("import os\nimport signal\ndef f(): " + body).status == "worker_failed"
    )


def test_exception_and_noisy_stdio_do_not_leak():
    source = "import os\nimport sys\ndef f():\n    print('database password = secret')\n    os.write(1,b'bad frame')\n    sys.stderr.write('private path /secret')\n    raise RuntimeError('database password = secret')"
    result = invoke(source)
    assert result.status == "execution_failed"
    assert "secret" not in result.model_dump_json()
    assert invoke("def f():\n    print('noise')\n    return 3").value == 3


@pytest.mark.parametrize(
    "body",
    [
        "return object()",
        "return {1}",
        "return (1,2)",
        'return b"x"',
        'return {1:"x"}',
        'return float("nan")',
    ],
)
def test_result_conversion_failure(body):
    assert invoke("def f(): " + body).status == "result_invalid"


def test_fresh_globals_defaults_environment_and_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("APIZR_TEST_SECRET", "super-secret")
    source = "import os\nfrom pathlib import Path\nstate=[]\ndef f(default=[]):\n    state.append(1)\n    default.append(1)\n    prior=Path('created').exists()\n    Path('created').touch()\n    os.environ['APIZR_CHILD_ONLY']='changed'\n    return [len(state),len(default),prior,'APIZR_TEST_SECRET' in os.environ]"
    runtime, raw = planned(source)
    for _ in range(2):
        assert execute(runtime, raw, {}).value == [1, 1, False, False]
    assert "APIZR_CHILD_ONLY" not in os.environ
    assert not (tmp_path / "created").exists()
    assert (
        invoke(
            "import os\ndef f(): return 'APIZR_TEST_SECRET' in os.environ",
            environment={"allow": ["APIZR_TEST_SECRET"]},
        ).value
        is True
    )
    assert (
        invoke(
            "import os\ndef f(): return 'APIZR_TEST_SECRET' in os.environ",
            environment={"inherit": True},
        ).value
        is True
    )
    assert "super-secret" not in runtime.model_dump_json()


def test_host_files_and_subprocess_are_not_falsely_isolated(tmp_path):
    marker = tmp_path / "host-visible"
    source = f"from pathlib import Path\nimport subprocess\nimport sys\ndef f():\n    Path({str(marker)!r}).write_text('visible')\n    return subprocess.run([sys.executable,'-I','-c','print(42)'],capture_output=True,text=True).stdout.strip()"
    assert invoke(source).value == "42"
    assert marker.read_text() == "visible"


@pytest.mark.parametrize(
    "code",
    [
        "import os; os.write(1,b'broken')",
        "import os,struct; os.write(1,struct.pack('!Q',10)+b'{}')",
        "import os,struct; os.write(1,struct.pack('!Q',99999999))",
        "import os; os._exit(3)",
        "import os; os.write(1,b'x'*300)",
    ],
)
def test_real_malformed_worker_cannot_hang(tmp_path, code):
    result = exchange([sys.executable, "-I", "-c", code], b"x", tmp_path, {}, 1000, 128)
    assert result.status in {"worker_failed", "output_limit"}


@settings(max_examples=8, deadline=None)
@given(st.integers(-100, 100), st.booleans())
def test_argument_transport_property(value, supply):
    payload = {"a": value}
    if supply:
        payload["b"] = value
    result = invoke("def f(a: int, /, *, b: int=3): return [a,b]", payload)
    assert result.value == [value, value if supply else 3]


@settings(max_examples=8, deadline=None)
@given(st.integers(0, 300))
def test_output_boundary_property(count):
    from apizr.execution.model import ExecutionResult
    from apizr.execution.protocol import encode

    encoded = encode(
        ExecutionResult(status="success", value="x" * count).model_dump(mode="json"),
        10000,
    )
    result = invoke(f"def f(): return 'x'*{count}", limits={"max_output_bytes": 128})
    assert result.status == ("success" if len(encoded) <= 128 else "output_limit")


@settings(max_examples=10)
@given(
    st.dictionaries(
        st.from_regex(r"APIZR_[A-Z]{1,8}", fullmatch=True),
        st.text(max_size=20),
        max_size=10,
    )
)
def test_environment_allowlist_property(parent):
    assert worker_environment(Environment(), parent) == {}
    names = sorted(parent)[::2]
    assert worker_environment(Environment(allow=tuple(names)), parent) == {
        name: parent[name] for name in names
    }
    assert worker_environment(Environment(inherit=True), parent) == parent


def test_host_network_is_not_falsely_isolated():
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(2)
        port = listener.getsockname()[1]
        result = invoke(
            f"import socket\ndef f():\n    with socket.create_connection(('127.0.0.1',{port}),timeout=1) as connection:\n        connection.sendall(b'ok')\n    return True"
        )
        assert result.value is True
        connection, _ = listener.accept()
        with connection:
            assert connection.recv(2) == b"ok"


def test_real_worker_source_tampering_and_binding_conflict(tmp_path):
    from apizr.execution import ExecutionPolicy, plan
    from apizr.execution.protocol import encode, frame
    from apizr.inspection import inspect_source

    from .helpers import request_root

    with request_root(tmp_path, "def f(): return 1") as request:
        (tmp_path / request.plan.executable_path).write_bytes(
            b'raise RuntimeError("must not execute")'
        )
        result = exchange(
            [sys.executable, "-I", "-m", "apizr.execution.worker"],
            frame(encode(request.model_dump(mode="json"), 100000)),
            tmp_path,
            {},
            5000,
            10000,
        )
        assert result.status == "source_mismatch"
    source = b"def f(): return 1"
    runtime = plan(
        inspect_source(source, module_name="sys"), source, "f", ExecutionPolicy()
    )
    assert execute(runtime, source, {}).status == "binding_failed"


def test_plan_refusal_and_spawn_failure_are_sanitized(monkeypatch):
    from apizr.execution import supervisor
    from apizr.execution.policy import PolicyRefused

    runtime, source = planned("def f(): return 1")
    assert execute(runtime, source + b"#different", {}).status == "binding_failed"

    def fail(*args, **kwargs):
        raise OSError("private executable path")

    monkeypatch.setattr(supervisor.subprocess, "Popen", fail)
    assert execute(runtime, source, {}).status == "worker_failed"

    def refuse(*args):
        raise PolicyRefused("unsupported_control")

    monkeypatch.setattr(supervisor, "validate_plan", refuse)
    assert execute(runtime, source, {}).status == "policy_refused"


@pytest.mark.parametrize(
    "code,status",
    [
        ("import os,time; os.close(1); time.sleep(10)", "timeout"),
        ("import os; os.close(0); os._exit(1)", "worker_failed"),
        (
            'import os,struct; b=b\'{"schema_version":"apizr.execution-result/v1","status":"timeout","value":"secret"}\'; os.write(1,struct.pack(\'!Q\',len(b))+b)',
            "worker_failed",
        ),
    ],
)
def test_protocol_exit_and_failure_envelope(tmp_path, code, status):
    assert (
        exchange(
            [sys.executable, "-I", "-c", code], b"x" * 100000, tmp_path, {}, 500, 128
        ).status
        == status
    )


@settings(max_examples=5, deadline=None)
@given(
    st.dictionaries(
        st.from_regex(r"APIZR_PROPERTY_[A-Z]{1,4}", fullmatch=True),
        st.text(alphabet="abcdef123", max_size=10),
        min_size=1,
        max_size=4,
    )
)
def test_actual_worker_environment_property(parent):
    names = sorted(parent)
    with pytest.MonkeyPatch.context() as patch:
        for name, value in parent.items():
            patch.setenv(name, value)
        source = f"import os\ndef f(): return [name for name in {names!r} if name in os.environ]"
        assert invoke(source).value == []
        assert invoke(source, environment={"allow": names[::2]}).value == names[::2]


def test_ordinary_descendant_is_stopped_with_worker(tmp_path):
    import subprocess

    marker = tmp_path / "descendant"
    heartbeat = tmp_path / "heartbeat"
    child = f"import time\nfrom pathlib import Path\nwhile True:\n Path({str(heartbeat)!r}).write_text(str(time.monotonic()))\n time.sleep(.02)"
    source = f"import subprocess\nimport sys\nimport time\nfrom pathlib import Path\ndef f():\n    child=subprocess.Popen([sys.executable,'-I','-c',{child!r}])\n    Path({str(marker)!r}).write_text(str(child.pid))\n    time.sleep(3600)\n"
    result = invoke(source, limits={"wall_time_ms": 1200})
    assert result.status == "timeout"
    pid = int(marker.read_text())
    last = heartbeat.read_text()
    time.sleep(0.1)
    assert heartbeat.read_text() == last
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    # An orphan can briefly await host-init reaping, but cannot still execute.
    assert not state or state.startswith("Z")


def test_closed_pipes_do_not_evade_wall_deadline(tmp_path):
    code = "import os,time; os.read(0,1); os.close(0); os.close(1); time.sleep(10)"
    assert (
        exchange(
            [sys.executable, "-I", "-c", code], b"x", tmp_path, {}, 500, 128
        ).status
        == "timeout"
    )


def test_invalid_failure_value_is_never_public(tmp_path):
    code = 'import sys,struct; sys.stdin.buffer.read(); b=b\'{"schema_version":"apizr.execution-result/v1","status":"timeout","value":"secret"}\'; sys.stdout.buffer.write(struct.pack("!Q",len(b))+b)'
    result = exchange([sys.executable, "-I", "-c", code], b"x", tmp_path, {}, 1000, 128)
    assert result.status == "worker_failed" and result.value is None

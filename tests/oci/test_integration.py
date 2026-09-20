import concurrent.futures
import json
import socket
import subprocess
import sys
import time

import pytest

from apizr.oci.docker import DockerProvider
from apizr.oci.supervisor import execute

from .helpers import planned

pytestmark = pytest.mark.timeout(60)


class Observed(DockerProvider):
    name = None
    configuration = None

    def create(self, name, plan, root, environment):
        super().create(name, plan, root, environment)
        self.name = name
        self.configuration = json.loads(self.run(["inspect", name]))[0]

    def assert_removed(self):
        assert self.name
        assert not self.run(["ps", "-aq", "--filter", f"name=^/{self.name}$"]).strip()


def invoke(image, source, arguments=None, **changes):
    runtime, raw = planned(source, image=image, **changes)
    provider = Observed()
    result = execute(
        runtime, raw, {} if arguments is None else arguments, provider=provider
    )
    provider.assert_removed()
    return result, provider


@pytest.mark.parametrize(
    "source,args,status,value",
    [
        ("def f(a:int=3,/,*,b:int=2): return a+b", {}, "success", 5),
        ("def f(a:int=3,/,*,b:int=2): return a+b", {"a": 4, "b": 7}, "success", 11),
        ("async def f(x:int): return x+1", {"x": 2}, "success", 3),
        ('def f(): raise RuntimeError("DO_NOT_EXPOSE")', {}, "execution_failed", None),
        ("def f(): return {1,2}", {}, "result_invalid", None),
        ('def f(): return "a"*10000', {}, "output_limit", None),
        ("import os\ndef f(): os._exit(23)", {}, "worker_failed", None),
        ('def f(): print("protocol contamination"); return 1', {}, "success", 1),
    ],
)
def test_real_worker_protocol(worker_image, source, args, status, value):
    result, _ = invoke(worker_image, source, args, limits={"max_output_bytes": 1024})
    assert result.status == status, result
    assert result.value == value
    assert "DO_NOT_EXPOSE" not in result.model_dump_json()


def test_real_privilege_filesystem_and_resource_controls(worker_image, tmp_path):
    private = tmp_path / "host-marker"
    private.write_text("HOST_PRIVATE_VALUE")
    source = f"""import os
from pathlib import Path
def f():
    status = dict(line.split(":",1) for line in Path("/proc/self/status").read_text().splitlines())
    result = {{"uid":os.getuid(), "caps":status["CapEff"].strip(), "nnp":status["NoNewPrivs"].strip(), "seccomp":status["Seccomp"].strip(), "host_visible":Path({str(private)!r}).exists(), "socket":Path("/var/run/docker.sock").exists(), "source_readable":Path(__file__).is_file()}}
    for name, path in [("bundle", __file__), ("root", "/forbidden" )]:
        try:
            Path(path).write_text("forbidden")
            result[name] = True
        except OSError:
            result[name] = False
    Path("/tmp/scratch").write_text("scratch")
    result["scratch"] = Path("/tmp/scratch").read_text()
    return result
"""
    result, provider = invoke(
        worker_image, source, resources={"cpu_millis": 500, "pids": 32}
    )
    assert result.status == "success", result
    assert result.value == {
        "uid": 65532,
        "caps": "0000000000000000",
        "nnp": "1",
        "seccomp": "2",
        "host_visible": False,
        "socket": False,
        "source_readable": True,
        "bundle": False,
        "root": False,
        "scratch": "scratch",
    }
    config = provider.configuration["HostConfig"]
    assert config["ReadonlyRootfs"] and not config["Privileged"]
    assert config["NetworkMode"] == "none" and config["PidMode"] != "host"
    assert config["CapDrop"] == ["ALL"] and not config["Devices"]
    assert config["Memory"] == config["MemorySwap"] == 268435456
    assert config["CpuQuota"] == 50000 and config["CpuPeriod"] == 100000
    assert config["PidsLimit"] == 32
    mounts = provider.configuration["Mounts"]
    assert (
        len(mounts) == 1
        and mounts[0]["Destination"] == "/bundle"
        and not mounts[0]["RW"]
    )
    assert "noexec" in config["Tmpfs"]["/tmp"]
    assert config["ShmSize"] == 65536


def test_real_network_deny_with_host_listener(worker_image):
    with socket.socket() as listener:
        # Docker Desktop forwards the host alias to host services, including
        # loopback; Linux CI uses the concrete host interface. Avoid LAN firewall
        # interception on Desktop while retaining a real TCP listener/control.
        host_address = (
            "127.0.0.1"
            if sys.platform == "darwin"
            else socket.gethostbyname(socket.gethostname())
        )
        listener.bind((host_address, 0))
        listener.listen()
        listener.settimeout(1)
        port = listener.getsockname()[1]
        # Positive host-side control: the exact address/port really accepts TCP.
        # Bind one interface only, never expose a test listener on all interfaces.
        with socket.create_connection((host_address, port), timeout=1):
            accepted, _ = listener.accept()
            accepted.close()
        hosts = [host_address, "host.docker.internal"]
        source = f"""import socket
def f():
    results = []
    for host in {hosts!r}:
        try:
            connection = socket.create_connection((host,{port}), timeout=0.2)
            connection.close()
            results.append(True)
        except OSError:
            results.append(False)
    return results
"""
        result, _ = invoke(worker_image, source)
        assert result.value == [False] * len(hosts), result
        listener.settimeout(0.1)
        with pytest.raises(TimeoutError):
            listener.accept()


def test_real_environment_filter_and_no_values_in_arguments(worker_image, monkeypatch):
    marker = "oci-private-marker-do-not-disclose"
    monkeypatch.setenv("APIZR_ALLOWED", marker)
    monkeypatch.setenv("APIZR_HIDDEN", marker)
    commands = []
    original = DockerProvider.run

    def observed(self, arguments, **kwargs):
        commands.append(list(arguments))
        return original(self, arguments, **kwargs)

    monkeypatch.setattr(DockerProvider, "run", observed)
    source = """import os
def f():
    return {"allowed": os.environ.get("APIZR_ALLOWED") == "oci-private-marker-do-not-disclose", "hidden": "APIZR_HIDDEN" in os.environ, "names": sorted(os.environ)}
"""
    result, provider = invoke(
        worker_image, source, environment={"allow": ["APIZR_ALLOWED"]}
    )
    assert result.value == {
        "allowed": True,
        "hidden": False,
        "names": ["APIZR_ALLOWED"],
    }
    assert marker not in json.dumps(commands)
    assert marker not in result.model_dump_json()
    assert marker not in json.dumps(provider.configuration["Config"]["Labels"])


@pytest.mark.parametrize("body", ["while True: pass", "time.sleep(3600)"])
def test_real_timeout_removes_container(worker_image, body):
    started = time.monotonic()
    result, _ = invoke(
        worker_image, "import time\ndef f():\n    " + body, limits={"wall_time_ms": 700}
    )
    assert result.status == "timeout", result
    assert time.monotonic() - started < 10


def test_real_memory_limit_oom_evidence(worker_image):
    source = """def f():
    chunks = []
    for i in range(512):
        chunks.append(bytearray(1024*1024))
    return len(chunks)
"""
    result, _ = invoke(
        worker_image,
        source,
        resources={"memory_bytes": 100663296},
        limits={"wall_time_ms": 10000},
    )
    assert result.status == "resource_limit", result
    assert result.value is None


def test_real_pid_limit_contains_bounded_subprocess_loop(worker_image):
    source = """import subprocess
import sys
def f():
    children = []
    try:
        for i in range(40):
            children.append(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    except OSError:
        return len(children)
    finally:
        for child in children:
            child.kill()
            child.wait()
    return 40
"""
    result, _ = invoke(worker_image, source, resources={"pids": 12})
    assert result.status == "success" and 0 < result.value < 12, result


def test_real_detached_descendant_dies_with_container(worker_image):
    child = 'import os,time; os.setsid();\nwhile True:\n open("/tmp/heartbeat","w").write(str(time.monotonic_ns()))\n time.sleep(0.05)'
    source = f"""import subprocess
import sys
import time
def f():
    subprocess.Popen([sys.executable, "-c", {child!r}], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3600)
"""
    runtime, raw = planned(source, image=worker_image, limits={"wall_time_ms": 3000})
    provider = Observed()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        invocation = executor.submit(execute, runtime, raw, {}, provider=provider)
        beats = []
        deadline = time.monotonic() + 2.5
        while time.monotonic() < deadline and len(set(beats)) < 2:
            if provider.name:
                observation = subprocess.run(
                    [
                        "docker",
                        "exec",
                        provider.name,
                        "/usr/local/bin/python",
                        "-c",
                        'print(open("/tmp/heartbeat").read())',
                    ],
                    capture_output=True,
                    timeout=2,
                )
                if observation.returncode == 0:
                    beats.append(observation.stdout)
            time.sleep(0.05)
        assert len(set(beats)) >= 2, (
            "Detached child must demonstrably be alive before cleanup"
        )
        assert invocation.result(timeout=10).status == "timeout"
    provider.assert_removed()
    assert (
        subprocess.run(
            ["docker", "exec", provider.name, "cat", "/tmp/heartbeat"],
            capture_output=True,
        ).returncode
        != 0
    )
    time.sleep(0.15)
    provider.assert_removed()  # No namespace/container remains to produce later heartbeats.


def test_real_source_digest_mismatch_before_import(worker_image):
    class Tampered(Observed):
        def create(self, name, plan, root, environment):
            target = root / plan.worker.executable_path
            target.chmod(0o644)
            target.write_bytes(
                target.read_bytes() + b"\nraise RuntimeError('must not run')"
            )
            super().create(name, plan, root, environment)

    runtime, raw = planned(image=worker_image)
    provider = Tampered()
    result = execute(runtime, raw, {}, provider=provider)
    assert result.status == "source_mismatch"
    provider.assert_removed()


def test_real_readonly_mount_flags_cgroups_and_bounded_scratch(worker_image):
    source = """import os
from pathlib import Path
def f():
    result = {"root_ro": bool(os.statvfs("/").f_flag & os.ST_RDONLY), "bundle_ro": bool(os.statvfs("/bundle").f_flag & os.ST_RDONLY)}
    for name in ["memory.max", "cpu.max", "pids.max"]:
        path = Path("/sys/fs/cgroup") / name
        if path.exists():
            result[name] = path.read_text().strip()
    try:
        Path("/tmp/overflow").write_bytes(b"x"*2097152)
        result["scratch_full"] = False
    except OSError:
        result["scratch_full"] = True
    return result
"""
    result, _ = invoke(
        worker_image,
        source,
        resources={"scratch_bytes": 1048576, "cpu_millis": 500, "pids": 32},
    )
    assert result.status == "success", result
    assert (
        result.value["root_ro"]
        and result.value["bundle_ro"]
        and result.value["scratch_full"]
    )
    if (
        "memory.max" in result.value
    ):  # cgroup v2; v1 controls are also checked by inspect.
        assert result.value["memory.max"] == "268435456"
        assert result.value["cpu.max"] == "50000 100000"
        assert result.value["pids.max"] == "32"


def test_real_worker_rejects_malformed_protocol_frame(worker_image, monkeypatch):
    from apizr.oci import supervisor

    original = supervisor.exchange

    def malformed(command, payload, *args):
        return original(command, b"\x00" * 8, *args)

    monkeypatch.setattr(supervisor, "exchange", malformed)
    result, _ = invoke(worker_image, "def f(): return 1")
    assert result.status == "worker_failed"


def test_real_worker_verifies_symbol_even_for_internally_consistent_ir(worker_image):
    # Simulate an upstream analyzer defect: all metadata/digests agree with each
    # other, but assert a symbol absent from the exact bound source. Only runtime
    # binding verification can detect this; the planner must not reinterpret IR.
    from apizr.capabilities import CapabilityDocument, document_digest
    from apizr.inspection import Inspection, inspect_source
    from apizr.oci.model import ExecutionPolicyV2
    from apizr.oci.planner import plan
    from apizr.readiness import ReadinessReport, report_digest

    raw = b"def f(x:int=1): return x"
    inspection = inspect_source(raw, module_name="oci_sample")
    data = json.loads(
        inspection.model_dump_json()
        .replace('"f"', '"missing"')
        .replace("python:oci_sample:f", "python:oci_sample:missing")
    )
    ir = CapabilityDocument.model_validate(data["capability_ir"])
    ir_digest = document_digest(ir)
    data["readiness"]["ir_digest"] = ir_digest.model_dump(mode="json")
    readiness = ReadinessReport.model_validate(data["readiness"])
    inspection = Inspection(
        capability_ir=ir,
        ir_digest=ir_digest,
        readiness=readiness,
        readiness_digest=report_digest(readiness),
    )
    runtime = plan(inspection, raw, "missing", ExecutionPolicyV2(), worker_image)
    provider = Observed()
    assert execute(runtime, raw, {}, provider=provider).status == "binding_failed"
    provider.assert_removed()

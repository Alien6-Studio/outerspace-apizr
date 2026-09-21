import json
import subprocess

import pytest

from apizr.oci.docker import DockerProvider
from apizr.oci.provider import ProviderError

from .helpers import IMAGE, planned

HOST = {
    "OSType": "linux",
    "MemoryLimit": True,
    "SwapLimit": True,
    "CpuCfsQuota": True,
    "CpuCfsPeriod": True,
    "PidsLimit": True,
    "SecurityOptions": ["name=seccomp,profile=builtin"],
}
IMAGE_INFO = {
    "Id": IMAGE.image,
    "Os": "linux",
    "Architecture": "amd64",
    "Config": {"Labels": {"org.apizr.worker.protocol": "apizr.runtime/v1"}},
}


@pytest.mark.parametrize(
    "field,value",
    [
        ("OSType", "windows"),
        ("MemoryLimit", False),
        ("SwapLimit", False),
        ("CpuCfsQuota", False),
        ("CpuCfsPeriod", False),
        ("PidsLimit", False),
        ("SecurityOptions", []),
    ],
)
def test_probe_refuses_unenforceable_host(monkeypatch, field, value):
    monkeypatch.setattr(
        DockerProvider,
        "run",
        lambda *a, **k: json.dumps({**HOST, field: value}).encode(),
    )
    with pytest.raises(ProviderError, match="backend_unavailable"):
        DockerProvider().probe(IMAGE)


@pytest.mark.parametrize(
    "image",
    [
        {},
        {**IMAGE_INFO, "Id": "sha256:" + "1" * 64},
        {**IMAGE_INFO, "Architecture": "arm64"},
        {**IMAGE_INFO, "Config": {"Labels": {}}},
        {
            **IMAGE_INFO,
            "Config": {
                "Labels": {"org.apizr.worker.protocol": "apizr.runtime/v1"},
                "Volumes": {"/data": {}},
            },
        },
    ],
)
def test_probe_refuses_image_identity_contract_or_implicit_volumes(monkeypatch, image):
    monkeypatch.setattr(
        DockerProvider,
        "run",
        lambda self, args, **k: json.dumps(
            HOST if args[0] == "info" else image
        ).encode(),
    )
    with pytest.raises(ProviderError, match="runtime_image_unavailable"):
        DockerProvider().probe(IMAGE)


def test_probe_missing_image_invalid_host_and_valid_host(monkeypatch):
    def run(self, args, **kwargs):
        if args[0] == "image":
            raise ProviderError()
        return json.dumps(HOST).encode()

    monkeypatch.setattr(DockerProvider, "run", run)
    with pytest.raises(ProviderError, match="runtime_image_unavailable"):
        DockerProvider().probe(IMAGE)
    monkeypatch.setattr(DockerProvider, "run", lambda *a, **k: b"{}")
    with pytest.raises(ProviderError, match="backend_unavailable"):
        DockerProvider().probe(IMAGE)
    monkeypatch.setattr(
        DockerProvider,
        "run",
        lambda self, args, **k: json.dumps(
            HOST if args[0] == "info" else IMAGE_INFO
        ).encode(),
    )
    DockerProvider().probe(IMAGE)


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("PRIVATE"),
        subprocess.TimeoutExpired("PRIVATE", 1),
        subprocess.CalledProcessError(1, "PRIVATE", stderr=b"PRIVATE"),
    ],
)
def test_cli_errors_are_value_free(monkeypatch, failure):
    def fail(*args, **kwargs):
        assert "shell" not in kwargs
        raise failure

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(ProviderError) as result:
        DockerProvider().run(["info"])
    assert str(result.value) == "backend_unavailable"


def test_create_has_no_escape_hatches_or_environment_values(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        DockerProvider, "run", lambda self, args, **k: calls.append((args, k))
    )
    plan, _ = planned()
    DockerProvider().create("test", plan, tmp_path, {"MARKER": "PRIVATE"})
    args, kwargs = calls[0]
    for control in (
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        "--user=65532:65532",
        "--ipc=private",
        "--cgroupns=private",
        "--pids-limit",
        "--memory",
        "--memory-swap",
        "--cpu-quota",
    ):
        assert control in args
    assert "PRIVATE" not in str(args)
    assert kwargs["environment"]["MARKER"] == "PRIVATE"
    assert args[-1] == "MARKER"
    assert DockerProvider().command("test") == [
        "docker",
        "start",
        "--attach",
        "--interactive",
        "test",
    ]
    with pytest.raises(ProviderError):
        DockerProvider().create("test", plan, tmp_path / "comma,path", {})


@pytest.mark.parametrize(
    "scenario", ["success", "already_absent", "retry", "unreachable", "still_present"]
)
def test_cleanup_retries_and_reports_failure(monkeypatch, scenario):
    calls = []

    def run(self, args, **kwargs):
        calls.append(args)
        if scenario == "success" or (scenario == "retry" and len(calls) > 2):
            return b""
        if args[0] == "rm" or scenario == "unreachable":
            raise ProviderError()
        return b"present" if scenario in {"retry", "still_present"} else b""

    monkeypatch.setattr(DockerProvider, "run", run)
    if scenario in {"unreachable", "still_present"}:
        with pytest.raises(ProviderError, match="cleanup_failed"):
            DockerProvider().remove("test")
        assert sum(args[0] == "rm" for args in calls) == 3
    else:
        DockerProvider().remove("test")


def test_non_posix_supervision_and_unconfined_daemon_are_refused(monkeypatch):
    monkeypatch.setattr("apizr.oci.docker.os.name", "nt")
    with pytest.raises(ProviderError):
        DockerProvider().probe(IMAGE)
    monkeypatch.setattr("apizr.oci.docker.os.name", "posix")
    monkeypatch.setattr(
        DockerProvider,
        "run",
        lambda *a, **k: json.dumps(
            {**HOST, "SecurityOptions": ["name=seccomp,profile=unconfined"]}
        ).encode(),
    )
    with pytest.raises(ProviderError):
        DockerProvider().probe(IMAGE)

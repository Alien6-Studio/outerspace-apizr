import copy
import ctypes
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from oci.helpers import IMAGE, planned
from oci.test_provider import HOST, IMAGE_INFO
from repository_execution.helpers import planned as repository_planned

from apizr.capabilities.model import Digest
from apizr.execution.policy import PolicyRefused, Subprocess
from apizr.execution.serialization import digest
from apizr.inspection import inspect_source
from apizr.oci.docker import DockerProvider
from apizr.oci.model import ContainerResult, ExecutionPolicyV2
from apizr.oci.provider import ProviderError
from apizr.repository_execution.docker import RepositoryDockerProvider
from apizr.subprocess_guard import (
    entrypoint,
    filter,
    repository,
    repository_entrypoint,
    single,
)
from apizr.subprocess_guard.provider import LABEL, PROTOCOL, DenyDockerProvider


def deny(value):
    policy = value.policy.model_copy(update={"subprocess": Subprocess(mode="deny")})
    return value.model_copy(update={"policy": policy, "policy_digest": digest(policy)})


def test_single_bound_plan_refusals_and_delegate(monkeypatch):
    old, raw = planned()
    strict = single.plan(
        inspect_source(raw, module_name="oci_sample"), raw, "f", deny(old).policy, IMAGE
    )
    assert strict == deny(old)
    assert single.validate_plan(strict, raw, raw) == strict
    assert single.execute(old, raw, {}).status == "policy_refused"
    assert single.execute(strict, raw + b"# changed", {}).status == "binding_failed"
    assert (
        single.execute(
            strict.model_copy(update={"worker_digest": Digest.of_bytes(b"tampered")}),
            raw,
            {},
        ).status
        == "binding_failed"
    )
    assert (
        single.execute(strict, raw, {}, provider=DockerProvider()).status
        == "backend_unavailable"
    )

    def execute(inner, source, payload, **kwargs):
        assert inner == old and isinstance(kwargs["provider"], DenyDockerProvider)
        return ContainerResult(status="success", value=42)

    monkeypatch.setattr(single, "allow_execute", execute)
    assert single.execute(strict, raw, {}).value == 42
    strict_notebook = strict.model_copy(
        update={
            "worker": strict.worker.model_copy(
                update={
                    "source": strict.worker.source.model_copy(
                        update={"kind": "notebook"}
                    )
                }
            )
        }
    )
    assert single.execute(strict_notebook, raw, {}).status == "binding_failed"


def test_repository_bound_plan_refusals_and_delegate(monkeypatch):
    old, exposure, sources, _ = repository_planned(policy=ExecutionPolicyV2())
    strict = repository.container_plan(
        old.worker.repository_interface,
        exposure,
        old.worker.capability_id,
        deny(old).policy,
        IMAGE,
    )
    assert strict == deny(old)
    repository.validate_plan(strict, exposure)
    assert repository.execute(old, exposure, sources, {}).status == "policy_refused"
    assert (
        repository.execute(old.worker, exposure, sources, {}).status == "binding_failed"
    )
    assert (
        repository.execute(
            strict.model_copy(update={"worker_digest": Digest.of_bytes(b"tampered")}),
            exposure,
            sources,
            {},
        ).status
        == "binding_failed"
    )
    assert (
        repository.execute(
            strict, exposure, sources, {}, provider=RepositoryDockerProvider()
        ).status
        == "backend_unavailable"
    )

    def execute(inner, *args, **kwargs):
        assert inner == old and isinstance(
            kwargs["provider"], repository.DenyRepositoryProvider
        )
        return ContainerResult(status="success", value=42)

    monkeypatch.setattr(repository, "allow_execute", execute)
    assert repository.execute(strict, exposure, sources, {}).value == 42


@pytest.mark.parametrize("repository_mode", [False, True])
@pytest.mark.parametrize("label", [None, "old", PROTOCOL])
def test_provider_requires_independent_protocol_label(
    monkeypatch, repository_mode, label
):
    image = copy.deepcopy(IMAGE_INFO)
    image["Config"]["Labels"]["org.apizr.repository.worker.protocol"] = (
        "apizr.repository-runtime/v1"
    )
    if label is not None:
        image["Config"]["Labels"][LABEL] = label
    monkeypatch.setattr(
        DockerProvider,
        "run",
        lambda self, args, **k: json.dumps(
            HOST if args[0] == "info" else image
        ).encode(),
    )
    provider = (
        repository.DenyRepositoryProvider() if repository_mode else DenyDockerProvider()
    )
    if label == PROTOCOL:
        provider.probe(IMAGE)
    else:
        with pytest.raises(ProviderError, match="runtime_image_unavailable"):
            provider.probe(IMAGE)


@pytest.mark.parametrize("repository_mode", [False, True])
def test_create_preserves_controls_and_selects_strict_entrypoint(
    monkeypatch, tmp_path, repository_mode
):
    calls = []

    def run(*args, **kwargs):
        calls.append(args[0])
        return SimpleNamespace(stdout=b"id")

    monkeypatch.setattr("subprocess.run", run)
    if repository_mode:
        value, _, _, _ = repository_planned(policy=ExecutionPolicyV2())
        repository.DenyRepositoryProvider().create_repository(
            "name", value, tmp_path, {}
        )
    else:
        value, _ = planned()
        DenyDockerProvider().create("name", value, tmp_path, {})
    args = calls[0]
    assert (
        "apizr.subprocess_guard."
        + ("repository_entrypoint" if repository_mode else "entrypoint")
        in args
    )
    assert {
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        "--pids-limit",
    } <= set(args)


@pytest.mark.parametrize(
    "module, original",
    [
        (entrypoint, "apizr.oci.entrypoint"),
        (repository_entrypoint, "apizr.repository_execution.entrypoint"),
    ],
)
def test_filter_installs_before_worker_and_failure_never_falls_back(
    monkeypatch, module, original
):
    events = []
    monkeypatch.setattr(module, "install", lambda: events.append("filter"))
    monkeypatch.setattr(original + ".main", lambda: events.append("worker"))
    module.main()
    assert events == ["filter", "worker"]

    def fail():
        raise RuntimeError("kernel refused")

    monkeypatch.setattr(module, "install", fail)
    with pytest.raises(RuntimeError, match="kernel refused"):
        module.main()
    assert events == ["filter", "worker"]


def evaluate(machine, nr, arch):
    code, index, accumulator = filter.instructions(machine), 0, 0
    while True:
        operation, yes, no, value = code[index]
        if operation == 0x20:
            accumulator = arch if value == 4 else nr & 0xFFFFFFFF
        elif operation in {0x15, 0x35}:
            condition = (
                accumulator == value if operation == 0x15 else accumulator >= value
            )
            index += yes if condition else no
        elif operation == 0x06:
            return value
        else:
            raise AssertionError(operation)
        index += 1


@pytest.mark.parametrize(
    "machine,arch,forbidden,safe",
    [
        ("x86_64", 0xC000003E, [56, 57, 58, 59, 322, 435, 101, 425, 426, 427], 39),
        ("aarch64", 0xC00000B7, [220, 221, 281, 435, 117, 425, 426, 427], 172),
    ],
)
def test_bpf_denies_native_creation_compat_abis_and_x32_aliases(
    machine, arch, forbidden, safe
):
    for number in forbidden + [512, 520, -1, 0x40000000 + 59]:
        assert evaluate(machine, number, arch) == 0x00050001
    assert evaluate(machine, safe, arch) == 0x7FFF0000
    assert evaluate(machine, safe, 0x40000003) == 0x80000000
    with pytest.raises(RuntimeError, match="architecture"):
        filter.instructions("unknown")


@pytest.mark.parametrize(
    "results, error",
    [
        ([0, 1, 0, 2], None),
        ([-1], "no-new"),
        ([0, 0], "no-new"),
        ([0, 1, -1], "filter"),
        ([0, 1, 0, 0], "filter"),
    ],
)
def test_install_checks_kernel_returns(monkeypatch, results, error):
    monkeypatch.setattr(filter.sys, "platform", "linux")
    monkeypatch.setattr(filter.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(Path, "iterdir", lambda path: iter([Path("task")]))
    calls = []
    values = iter(results)

    def prctl(*args):
        calls.append(args)
        if args[0] == 22:
            program = ctypes.cast(args[2], ctypes.POINTER(filter.Program)).contents
            assert program.len > 6
        return next(values)

    monkeypatch.setattr(
        ctypes, "CDLL", lambda *args, **kwargs: SimpleNamespace(prctl=prctl)
    )
    if error:
        with pytest.raises(RuntimeError, match=error):
            filter.install()
    else:
        filter.install()
        assert [call[0] for call in calls] == [38, 39, 22, 21]


def test_install_refuses_other_platform_and_existing_threads(monkeypatch):
    monkeypatch.setattr(filter.sys, "platform", "darwin")
    with pytest.raises(RuntimeError, match="Linux"):
        filter.install()
    monkeypatch.setattr(filter.sys, "platform", "linux")
    monkeypatch.setattr(filter.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(Path, "iterdir", lambda path: iter([Path("1"), Path("2")]))
    with pytest.raises(RuntimeError, match="single-threaded"):
        filter.install()


@pytest.mark.parametrize(
    "name",
    [
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "GCONV_PATH",
        "GLIBC_TUNABLES",
        "PYTHONPATH",
        "DYLD_INSERT_LIBRARIES",
    ],
)
@pytest.mark.parametrize("module", [single, repository])
def test_strict_policy_refuses_bootstrap_environment(module, name):
    policy = ExecutionPolicyV2.model_validate(
        {"subprocess": {"mode": "deny"}, "environment": {"allow": [name]}}
    )
    with pytest.raises(PolicyRefused, match="unsupported_control"):
        module.relaxed(policy)


def test_cli_selects_deny_profile(tmp_path, monkeypatch, capsys):
    from apizr.execute_cli import main

    source, policy, args = (
        tmp_path / name for name in ["source.py", "policy.json", "args.json"]
    )
    source.write_text("def f(): return 1\n")
    policy.write_text(
        '{"schema_version":"apizr.execution/v2","subprocess":{"mode":"deny"}}'
    )
    args.write_text("{}")

    def invoke(plan, *a, **k):
        assert plan.policy.subprocess.mode == "deny"
        return ContainerResult(status="success", value=1)

    monkeypatch.setattr(single, "execute", invoke)
    assert (
        main(
            [
                str(source),
                "f",
                "--policy",
                str(policy),
                "--arguments",
                str(args),
                "--runtime-image",
                IMAGE.image,
                "--runtime-platform",
                IMAGE.platform,
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["value"] == 1

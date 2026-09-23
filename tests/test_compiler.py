"""Python/CLI parity over existing contracts, refusals and discovery boundaries."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from apizr.cli import main
from apizr.compiler import assess_readiness, prepare_exposure, render_bundle
from apizr.execution.policy import ExecutionPolicy, PolicyRefused
from apizr.exposure import ExposurePolicy, ExposureRefused, plan_bytes, refusal_report
from apizr.graph import GraphPolicy
from apizr.oci.model import ExecutionPolicyV2, RuntimeImage
from apizr.repository import ScanPolicy
from apizr.repository_interfaces import BundleRefused
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_readiness import RepositoryReadinessPolicy, report_bytes

FIXTURES = Path(__file__).parent / "fixtures"
IMAGE = RuntimeImage(image="sha256:" + "0" * 64, platform="linux/amd64")


def exposure_policy(mode="direct", selected=("python:sample:add",)):
    return ExposurePolicy.model_validate(
        {
            "selection": {"include": selected},
            "interfaces": ["rest", "mcp"],
            "execution": {"allowed": [mode]},
        }
    )


def readiness_policy(mode="direct"):
    return RepositoryReadinessPolicy.model_validate({"execution": {"modes": [mode]}})


def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "sample.py").write_text(
        "def add(a: int, b: int = 1) -> int: return a + b\n"
    )
    return root


def policy_file(tmp_path, name, policy):
    path = tmp_path / name
    path.write_text(policy.model_dump_json())
    return str(path)


@pytest.mark.parametrize(
    "name", [None, "ungoverned", "governed-local", "isolated-oci", "impossible"]
)
def test_readiness_python_cli_and_existing_golden(tmp_path, capfd, name):
    root = tmp_path / "project"
    fixture = FIXTURES / "repository_readiness/completion"
    shutil.copytree(fixture / "project", root)
    policy_path = Path(__file__).parents[1] / f"examples/readiness/{name}.json"
    policy = (
        RepositoryReadinessPolicy.model_validate_json(policy_path.read_bytes())
        if name
        else None
    )
    scan = ScanPolicy(
        source_roots=("src",),
        excluded_directories=(*ScanPolicy().excluded_directories, "ignored"),
    )
    report = assess_readiness(root, scan_policy=scan, readiness_policy=policy)
    assert capfd.readouterr() == ("", "")
    flags = ["--policy", str(policy_path)] if name else []
    assert (
        main(
            [
                "readiness",
                str(root),
                "--source-root",
                "src",
                "--exclude-dir",
                "ignored",
                "--report",
                *flags,
            ]
        )
        == report.exit_code
    )
    captured = capfd.readouterr()
    assert not captured.err
    assert captured.out.encode() == report_bytes(report)
    if name is None:
        assert (
            report_bytes(report) == (fixture / "repo-default-report.json").read_bytes()
        )


def test_exposure_python_cli_and_existing_golden(capfd):
    fixture = FIXTURES / "exposure/v1"
    policy = ExposurePolicy.model_validate_json((fixture / "policy.json").read_bytes())
    prepared = prepare_exposure(fixture / "project", policy=policy)
    assert capfd.readouterr() == ("", "")
    assert (
        main(
            [
                "expose",
                "plan",
                str(fixture / "project"),
                "--policy",
                str(fixture / "policy.json"),
                "--plan",
            ]
        )
        == 0
    )
    assert capfd.readouterr().out.encode() == plan_bytes(prepared.plan)
    assert plan_bytes(prepared.plan) == (fixture / "plan.json").read_bytes()


@pytest.mark.parametrize("interface", ["rest", "mcp"])
@pytest.mark.parametrize("mode", ["direct", "local-process", "oci-container"])
def test_bundle_python_cli_exact_bytes_and_separate_safe_write(
    tmp_path, capfd, interface, mode
):
    root = project(tmp_path)
    policy, readiness = exposure_policy(mode), readiness_policy(mode)
    execution = {
        "direct": None,
        "local-process": ExecutionPolicy(),
        "oci-container": ExecutionPolicyV2(),
    }[mode]
    image = IMAGE if mode == "oci-container" else None
    prepared = prepare_exposure(root, policy=policy, readiness_policy=readiness)
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    bundle = render_bundle(
        prepared, interface=interface, execution_policy=execution, runtime_image=image
    )
    assert {p.relative_to(tmp_path) for p in tmp_path.rglob("*")} == before
    assert capfd.readouterr() == ("", "")
    output = tmp_path / "cli"
    flags = [
        "--policy",
        policy_file(tmp_path, "exposure.json", policy),
        "--readiness-policy",
        policy_file(tmp_path, "readiness.json", readiness),
    ]
    if execution is not None:
        flags += [
            "--execution-policy",
            policy_file(tmp_path, "execution.json", execution),
        ]
    if image is not None:
        flags += ["--runtime-image", image.image, "--runtime-platform", image.platform]
    assert (
        main(
            [
                "expose",
                "build",
                interface,
                str(root),
                *flags,
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    assert "bundle generated" in capfd.readouterr().out
    assert {
        p.relative_to(output).as_posix(): p.read_bytes()
        for p in output.rglob("*")
        if p.is_file()
    } == bundle
    assert bundle["repository-readiness.json"] == report_bytes(prepared.readiness)
    assert bundle["exposure-plan.json"] == plan_bytes(prepared.plan)
    destination = tmp_path / "python"
    write_bundle(destination, bundle)
    with pytest.raises(ValueError):
        write_bundle(destination, bundle)
    assert {
        p.relative_to(destination).as_posix(): p.read_bytes()
        for p in destination.rglob("*")
        if p.is_file()
    } == bundle


def test_retained_sources_one_discovery_even_after_deletion(
    tmp_path, monkeypatch, capfd
):
    import apizr.graph.builder as builder
    import apizr.repository.discovery as discovery

    root = project(tmp_path)
    original = (root / "sample.py").read_bytes()
    discover, read = builder.discover, discovery.read_source
    calls, reads = [], []

    def counted(*args, **kwargs):
        calls.append(args[0])
        return discover(*args, **kwargs)

    def counted_read(*args, **kwargs):
        reads.append(args[2])
        return read(*args, **kwargs)

    monkeypatch.setattr(builder, "discover", counted)
    monkeypatch.setattr(discovery, "read_source", counted_read)
    prepared = prepare_exposure(
        root, policy=exposure_policy(), readiness_policy=readiness_policy()
    )
    shutil.rmtree(root)
    for interface in ("rest", "mcp"):
        assert (
            render_bundle(prepared, interface=interface)["source/sample.py"] == original
        )
    assert calls == [root] and reads == ["sample.py"]
    assert capfd.readouterr() == ("", "")


@pytest.mark.parametrize(
    "document",
    [
        {"interfaces": [], "execution": {"allowed": ["direct"]}},
        {"interfaces": ["rest"], "execution": {"allowed": ["invented"]}},
        {
            "interfaces": ["rest"],
            "execution": {"allowed": ["direct"]},
            "selection": {"include": ["not-an-id"]},
        },
    ],
)
def test_invalid_exposure_policy_python_and_cli(tmp_path, capfd, document):
    with pytest.raises(ValidationError):
        ExposurePolicy.model_validate(document)
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(document))
    assert main(["expose", "plan", str(tmp_path), "--policy", str(path)]) == 2
    captured = capfd.readouterr()
    assert not captured.out and "invalid/inaccessible policy" in captured.err


@pytest.mark.parametrize("kind", ["scan", "graph", "readiness"])
def test_invalid_typed_policy_preserves_validation(tmp_path, capfd, kind):
    # model_copy deliberately bypasses Pydantic validation: the compiler must
    # retain the existing consumers' revalidation, not trust a typed instance.
    policy, flag, field = {
        "scan": (ScanPolicy(), "--max-file-bytes", "max_file_bytes"),
        "graph": (GraphPolicy(), "--max-ast-nodes", "max_ast_nodes"),
        "readiness": (RepositoryReadinessPolicy(), None, "schema_version"),
    }[kind]
    invalid = policy.model_copy(update={field: 0})
    for operation in (assess_readiness, prepare_exposure):
        kwargs = {f"{kind}_policy": invalid}
        if operation is prepare_exposure:
            kwargs["policy"] = exposure_policy()
        with pytest.raises(ValidationError):
            operation(tmp_path, **kwargs)
    assert capfd.readouterr() == ("", "")
    flags = (
        [flag, "0"]
        if flag
        else ["--policy", policy_file(tmp_path, "invalid.json", invalid)]
    )
    assert main(["readiness", str(tmp_path), *flags]) == 2
    assert "invalid policy/input" in capfd.readouterr().err


@pytest.mark.parametrize("selected", ["python:sample:missing", "python:sample:bad"])
def test_refused_capabilities_same_structured_diagnostics(tmp_path, capfd, selected):
    root = project(tmp_path)
    with (root / "sample.py").open("a") as stream:
        stream.write("def bad(*args): return args\n")
    policy = exposure_policy(selected=(selected,))
    readiness = readiness_policy()
    with pytest.raises(ExposureRefused) as refused:
        prepare_exposure(root, policy=policy, readiness_policy=readiness)
    assert refused.value.diagnostics
    assert capfd.readouterr() == ("", "")
    assert (
        main(
            [
                "expose",
                "plan",
                str(root),
                "--policy",
                policy_file(tmp_path, "policy.json", policy),
                "--readiness-policy",
                policy_file(tmp_path, "readiness.json", readiness),
            ]
        )
        == 1
    )
    captured = capfd.readouterr()
    assert not captured.out and captured.err == refusal_report(refused.value, policy)


def test_empty_selection_and_execution_refusals_remain_distinct(tmp_path, capfd):
    root = project(tmp_path)
    empty = prepare_exposure(
        root, policy=exposure_policy(selected=()), readiness_policy=readiness_policy()
    )
    assert empty.plan.capabilities == ()
    with pytest.raises(BundleRefused, match="APIZR-BUNDLE-002"):
        render_bundle(empty, interface="rest")
    prepared = prepare_exposure(root, policy=exposure_policy("local-process"))
    with pytest.raises(BundleRefused):
        render_bundle(prepared, interface="rest")  # No implicit backend fallback.
    with pytest.raises(PolicyRefused):
        render_bundle(
            prepared,
            interface="rest",
            execution_policy=ExecutionPolicy.model_validate(
                {"subprocess": {"mode": "deny"}}
            ),
        )
    with pytest.raises(ValueError, match="OCI requires"):
        render_bundle(prepared, interface="rest", execution_policy=ExecutionPolicyV2())
    with pytest.raises(ValueError, match="Runtime image requires"):
        render_bundle(prepared, interface="rest", runtime_image=IMAGE)
    assert capfd.readouterr() == ("", "")


def test_python_api_has_no_cli_import_execution_or_plugin_discovery(tmp_path):
    root = project(tmp_path)
    (root / "hostile.py").write_text(
        'import socket, subprocess\nopen("MARKER", "w").write("executed")\nraise RuntimeError("source executed")\n'
    )
    probe = """import os, sys
root = sys.argv[1]
def audit(event, args):
    if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "socket.connect", "socket.bind", "socket.getaddrinfo"}:
        raise AssertionError(event)
    if event == "import" and (args[0].split(".")[0] in {"hostile", "sample", "fastapi", "mcp", "nbconvert", "IPython", "black", "questionary", "docker"} or args[0] == "apizr.cli" or args[0].endswith("_cli")):
        raise AssertionError(args[0])
    if event == "exec" and str(args[0].co_filename).startswith(root):
        raise AssertionError("source execution")
    if event == "open" and isinstance(args[0], str) and args[0].startswith(root) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
        raise AssertionError("source write")
sys.addaudithook(audit)
import importlib.metadata
def forbidden(*args, **kwargs): raise AssertionError("plugin discovery")
importlib.metadata.entry_points = forbidden
from apizr.compiler import assess_readiness, prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy
from apizr.repository_readiness import RepositoryReadinessPolicy
assess_readiness(root)
policy = ExposurePolicy.model_validate({"selection":{"include":["python:sample:add"]},"interfaces":["rest","mcp"],"execution":{"allowed":["direct"]}})
readiness = RepositoryReadinessPolicy.model_validate({"execution":{"modes":["direct"]}})
prepared = prepare_exposure(root, policy=policy, readiness_policy=readiness)
assert not any(name.startswith("apizr.generators") for name in sys.modules)
for interface in ("rest", "mcp"):
    assert render_bundle(prepared, interface=interface)
assert not any(name.startswith("apizr.extensions.plugins") for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(root)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": "/nonexistent",
            "DOCKER_HOST": "invalid://not-assessed",
        },
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == result.stderr == b""
    assert not (root / "MARKER").exists()

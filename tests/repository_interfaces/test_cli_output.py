"""Single-discovery CLI, audit boundary and atomic output publication."""

import os
import subprocess
import sys

import pytest

from apizr.cli import main
from apizr.repository_interfaces.output import write_bundle


def flags(root, output, readiness, target="rest"):
    return [
        "expose",
        "build",
        target,
        str(root),
        "--interface",
        target,
        "--execution-mode",
        "direct",
        "--select",
        "python:a:f",
        "--readiness-policy",
        str(readiness),
        "--output-dir",
        str(output),
    ]


def setup(root):
    root.mkdir()
    (root / "a.py").write_text("def f(): return 1\n")
    rp = root.parent / "readiness.json"
    rp.write_text('{"execution":{"modes":["direct"]}}')
    return rp


@pytest.mark.parametrize("target", ["rest", "mcp"])
def test_cli_one_discovery_exact_retained_bytes(tmp_path, monkeypatch, capfd, target):
    import apizr.graph.builder as builder
    import apizr.repository.discovery as discovery

    root, output = tmp_path / "project", tmp_path / "bundle"
    rp = setup(root)
    original = (root / "a.py").read_bytes()
    discover, read, assemble = builder.discover, discovery.read_source, builder.assemble
    calls, reads = [], []

    def counted(*args):
        calls.append(1)
        return discover(*args)

    def counted_read(*args):
        reads.append(args[2])
        return read(*args)

    def changed(*args):
        result = assemble(*args)
        (root / "a.py").write_text('raise RuntimeError("changed")')
        return result

    monkeypatch.setattr(builder, "discover", counted)
    monkeypatch.setattr(discovery, "read_source", counted_read)
    monkeypatch.setattr(builder, "assemble", changed)
    assert main(flags(root, output, rp, target)) == 0
    assert "bundle generated" in capfd.readouterr().out
    assert (output / "source/a.py").read_bytes() == original
    assert calls == [1] and reads == ["a.py"]
    assert (
        main(flags(root, output, rp, target)) == 1
    )  # Changed source is no longer eligible.


def test_cli_invalid_refused_and_nonempty(tmp_path, capfd):
    root, output = tmp_path / "project", tmp_path / "bundle"
    rp = setup(root)
    args = flags(root, output, rp)
    no_selection = args[: args.index("--select")] + args[args.index("--select") + 2 :]
    assert main(no_selection) == 1
    assert "APIZR-BUNDLE-002" in capfd.readouterr().err
    assert not output.exists()
    assert main([*args, "--policy", "missing"]) == 2
    assert not output.exists()
    assert main(args) == 0
    before = {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }
    assert main(args) == 2
    assert {
        p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()
    } == before


@pytest.mark.parametrize("exists", [True, False])
def test_write_failure_leaves_no_partial_output(tmp_path, monkeypatch, exists):
    output = tmp_path / "bundle"
    if exists:
        output.mkdir()
    original = os.fdopen

    def fail(descriptor, mode):
        os.close(descriptor)
        raise OSError("injected disk failure")

    monkeypatch.setattr(os, "fdopen", fail)
    with pytest.raises(OSError):
        write_bundle(output, {"a.py": b"a", "sub/b.py": b"b"})
    assert not output.exists() or list(output.iterdir()) == []
    assert not list(tmp_path.glob(".apizr-stage-*"))
    monkeypatch.setattr(os, "fdopen", original)
    write_bundle(output, {"a.py": b"a", "sub/b.py": b"b"})
    assert (output / "sub/b.py").read_bytes() == b"b"


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a//b", "a\\b", "."])
def test_bad_artifact_path_no_writes(tmp_path, name):
    with pytest.raises(ValueError):
        write_bundle(tmp_path / "out", {name: b""})
    assert list(tmp_path.iterdir()) == []


def test_output_symlinks_traversal_existing_files_and_publish_race(
    tmp_path, monkeypatch
):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    for path in (link, link / "bundle", tmp_path / ".." / "escape"):
        with pytest.raises((OSError, ValueError)):
            write_bundle(path, {"a.py": b"a"})
    file = tmp_path / "file"
    file.write_text("keep")
    with pytest.raises(ValueError):
        write_bundle(file, {"a.py": b"a"})
    assert file.read_text() == "keep" and list(outside.iterdir()) == []
    rename = os.rename

    def raced(source, destination, **kwargs):
        fd = kwargs["dst_dir_fd"]
        os.mkdir(destination, dir_fd=fd)
        (tmp_path / destination / "concurrent").write_text("keep")
        return rename(source, destination, **kwargs)

    monkeypatch.setattr(os, "rename", raced)
    with pytest.raises(OSError):
        write_bundle(tmp_path / "race", {"a.py": b"a"})
    assert (tmp_path / "race/concurrent").read_text() == "keep"
    assert not list(tmp_path.glob(".apizr-stage-*"))


def test_generation_audit_no_project_execution_or_environment_probes(tmp_path):
    root = tmp_path / "project"
    rp = setup(root)
    (root / "hostile.py").write_text(
        'import socket, subprocess\nopen("MARKER", "w").write("executed")\nsocket.create_connection(("localhost", 9))\nsubprocess.run(["docker", "info"])\n'
    )
    probe = """import sys, os
root, output, readiness = sys.argv[1:]
def audit(event, args):
 if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "socket.connect", "socket.bind", "socket.getaddrinfo"}: raise AssertionError(event)
 if event == "import" and args[0].split('.')[0] in {"a", "hostile", "setup", "fastapi", "mcp", "docker"}: raise AssertionError(args[0])
 if event == "exec" and str(args[0].co_filename).startswith(root): raise AssertionError("project execution")
sys.addaudithook(audit)
from apizr.cli import main
import apizr.exposure_cli
import apizr.execution.policy
import importlib.util, importlib.metadata
def forbidden(*args, **kwargs): raise AssertionError("runtime/package probe")
apizr.execution.policy.local_capabilities = forbidden
importlib.util.find_spec = forbidden
importlib.metadata.distributions = forbidden
for target in ("rest", "mcp"):
 assert main(["expose", "build", target, root, "--interface", target, "--execution-mode", "direct", "--select", "python:a:f", "--readiness-policy", readiness, "--output-dir", output + target]) == 0
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            probe,
            str(root),
            str(tmp_path / "bundle"),
            str(rp),
        ],
        cwd=root,
        env={
            **os.environ,
            "PATH": "/nonexistent",
            "DOCKER_HOST": "invalid://not-assessed",
        },
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert not (root / "MARKER").exists()

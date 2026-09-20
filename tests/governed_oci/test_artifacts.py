import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from oci.helpers import IMAGE

from apizr.execution import ExecutionPolicy
from apizr.generate_cli import main
from apizr.generators.mcp import render as mcp_render
from apizr.generators.rest import render as rest_render
from apizr.governed.embedding import source
from apizr.governed_oci.model import BRIDGE_MODULES, OCI_MODULES
from apizr.inspection import inspect_source
from apizr.oci.model import ExecutionPolicyV2


@pytest.mark.parametrize(
    "render,transport,document",
    [(rest_render, "rest", "openapi.json"), (mcp_render, "mcp", "mcp-tools.json")],
)
def test_static_generation_preserves_interface_and_embeds_reviewed_code(
    render, transport, document, monkeypatch
):
    raw = b"def f(a:int=1,/,*,b:int=2): return a+b"
    inspected = inspect_source(raw, module_name="golden.oci_transport")

    def forbidden(*args, **kwargs):
        pytest.fail("generation performed runtime activity")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr("socket.socket", forbidden)
    monkeypatch.setattr("apizr.oci.docker.DockerProvider.probe", forbidden)
    direct = render(inspected, raw)
    local = render(inspected, raw, execution_policy=ExecutionPolicy())
    files = render(
        inspected, raw, execution_policy=ExecutionPolicyV2(), runtime_image=IMAGE
    )
    assert files[document] == local[document] == direct[document]
    for name in (*OCI_MODULES, *BRIDGE_MODULES, f"governed_oci/{transport}.py"):
        assert (
            files["apizr_governed/" + name]
            == source(name).replace("from apizr.", "from apizr_governed.").encode()
        )
    assert not any(
        "analyzer" in path or "notebook_transformr" in path for path in files
    )
    assert b"outerspace-apizr" not in files["requirements.txt"]
    manifest = f"apizr-{transport}.json"
    assert (
        files[manifest]
        == (
            Path(__file__).parents[1]
            / f"fixtures/governed_oci/{transport}-manifest.json"
        ).read_bytes()
    )
    bridge = json.loads(files["execution/bundle.json"])
    assert bridge["schema_version"] == "apizr.execution-bundle/v2"
    assert bridge["runtime"]["image"] == IMAGE.image
    assert (
        json.loads(files["execution/plans/f.json"])["schema_version"]
        == "apizr.runtime/v2"
    )


@settings(max_examples=5, deadline=None)
@given(
    st.integers(10, 2000),
    st.lists(st.sampled_from(["LANG", "APIZR_TEST_SECRET"]), max_size=4),
)
def test_deterministic_per_capability_plans(cpu, names):
    raw = b"def f(x:int): return x\nasync def g(): return 1"
    inspection = inspect_source(raw, module_name="deterministic.module")
    first = ExecutionPolicyV2.model_validate(
        {"resources": {"cpu_millis": cpu}, "environment": {"allow": names}}
    )
    second = ExecutionPolicyV2.model_validate(
        {
            "environment": {"allow": list(reversed(names))},
            "resources": {"cpu_millis": cpu},
        }
    )
    for render in [rest_render, mcp_render]:
        a = render(inspection, raw, execution_policy=first, runtime_image=IMAGE)
        assert a == render(
            inspection, raw, execution_policy=second, runtime_image=IMAGE
        )
        assert a["execution/plans/f.json"] != a["execution/plans/g.json"]
        selected = render(
            inspection, raw, select=["g"], execution_policy=first, runtime_image=IMAGE
        )
        assert "execution/plans/f.json" not in selected


@pytest.mark.parametrize("render", [rest_render, mcp_render])
def test_api_option_combinations_fail_closed(render):
    raw = b"def f(): return 1"
    inspected = inspect_source(raw, module_name="options")
    for policy, image in [
        (None, IMAGE),
        (ExecutionPolicy(), IMAGE),
        (ExecutionPolicyV2(), None),
    ]:
        with pytest.raises(ValueError):
            render(inspected, raw, execution_policy=policy, runtime_image=image)


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_cli_requires_explicit_options_and_reports_backend(tmp_path, capsys, transport):
    source_path = tmp_path / "sample.py"
    source_path.write_text("def f(): return 1")
    policy = tmp_path / "policy.json"
    policy.write_text('{"schema_version":"apizr.execution/v2"}')
    args = [
        transport,
        str(source_path),
        "--output-dir",
        str(tmp_path / "out"),
        "--execution-policy",
        str(policy),
    ]
    assert main(args) == 2
    assert "requires --runtime-image" in capsys.readouterr().err
    assert (
        main(
            [
                *args,
                "--runtime-image",
                "python:3.14-slim",
                "--runtime-platform",
                "linux/amd64",
            ]
        )
        == 2
    )
    capsys.readouterr()
    assert (
        main(
            [
                *args,
                "--runtime-image",
                IMAGE.image,
                "--runtime-platform",
                IMAGE.platform,
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["execution"]["backend"] == "oci-container"
    assert report["execution"]["provider"] == "docker-engine"
    assert IMAGE.image not in json.dumps(report)
    policy.write_text("{}")
    assert main([*args, "--runtime-image", IMAGE.image]) == 2
    capsys.readouterr()
    policy.write_bytes(b"x" * 1048577)
    assert main(args) == 2
    assert "size limit" in capsys.readouterr().err


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_generation_audit_hook_no_import_no_docker(tmp_path, transport):
    source_path = tmp_path / "hostile_target.py"
    source_path.write_text('def f(): raise RuntimeError("never run")')
    policy = tmp_path / "policy.json"
    policy.write_text('{"schema_version":"apizr.execution/v2"}')
    probe = """import sys
source=sys.argv[1]
def guard(event,args):
    if event in {"subprocess.Popen","socket.connect","os.system"}: raise AssertionError(event)
    if event=="import" and args[0]=="hostile_target": raise AssertionError("source import")
    if event=="exec" and args[0].co_filename==source: raise AssertionError("source execution")
sys.addaudithook(guard)
from apizr.generate_cli import main
raise SystemExit(main([sys.argv[4],source,"--execution-policy",sys.argv[2],"--output-dir",sys.argv[3],"--runtime-image",sys.argv[5],"--runtime-platform","linux/amd64"]))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            probe,
            str(source_path),
            str(policy),
            str(tmp_path / "out"),
            transport,
            IMAGE.image,
        ],
        cwd=tmp_path,
        env={**os.environ, "PATH": "/nonexistent"},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_local_startup_does_not_import_or_probe_docker(tmp_path, transport):
    from apizr.generators.mcp import generate as mcp_generate
    from apizr.generators.rest import generate as rest_generate

    raw = b"def f(): return 1"
    root = tmp_path / "local"
    (rest_generate if transport == "rest" else mcp_generate)(
        inspect_source(raw, module_name="local_sample"),
        raw,
        root,
        execution_policy=ExecutionPolicy(),
    )
    assert not (root / "apizr_governed/oci").exists()
    probe = """import sys,runpy
from pathlib import Path
def audit(event,args):
    if event=="subprocess.Popen" and "docker" in str(args[0]):raise AssertionError("Docker probe")
    if event=="import" and ".oci" in args[0]:raise AssertionError("OCI imported")
sys.addaudithook(audit)
root=Path(sys.argv[1]); transport=sys.argv[2]
if transport=="rest":runpy.run_path(str(root/"app.py"))
else:
    module=runpy.run_path(str(root/"server.py"))
    from apizr_governed.governed.mcp import create_server
    create_server(root)
assert "local_sample" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(root), transport],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr

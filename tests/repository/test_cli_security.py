import json
import os
import subprocess
import sys

from apizr.cli import main
from apizr.repository import Catalog, scan_sources
from apizr.repository.reporting import text_report


def test_cli_reports_envelope_canonical_and_exit_status(tmp_path, capfd):
    (tmp_path / "a.py").write_text("def f(): return 1")
    assert main(["scan", str(tmp_path)]) == 0
    assert "Sources: 1" in capfd.readouterr().out
    assert main(["scan", str(tmp_path), "--format", "json"]) == 0
    envelope = json.loads(capfd.readouterr().out)
    assert envelope["statistics"]["capabilities"] == 1
    assert main(["scan", str(tmp_path), "--catalog"]) == 0
    canonical = capfd.readouterr().out.encode()
    assert (
        Catalog.model_validate_json(canonical).model_dump(mode="json")
        == envelope["catalog"]
    )
    assert str(tmp_path).encode() not in canonical
    (tmp_path / "bad.py").write_text("invalid !")
    assert main(["scan", str(tmp_path), "--details"]) == 1
    assert "APIZR-REPO-008" in capfd.readouterr().out
    assert main(["scan", str(tmp_path / "missing")]) == 2
    assert "Traceback" not in capfd.readouterr().err
    assert main(["scan", str(tmp_path), "--source-root", "../outside"]) == 2
    capfd.readouterr()
    assert main(["--help"]) == 0
    assert "apizr scan ROOT" in capfd.readouterr().out


def test_bounded_human_output_and_detailed_diagnostics():
    raw = b"def f(): pass\ndef f(): pass\n" + b"\n".join(
        f"def f{i}(): yield 1".encode() for i in range(12)
    )
    files = [(f"a{i}.py", raw) for i in range(25)] + [
        (f"bad-{i}.py", b"pass") for i in range(12)
    ]
    catalog = scan_sources(files)
    concise = text_report(catalog)
    expanded = text_report(catalog, details=True)
    assert "Further assessments omitted" in concise
    assert "Further sources omitted" in concise
    assert "Further diagnostics omitted" in concise
    assert "omitted;" not in expanded
    assert "APIZR-CAP-001" in expanded
    assert len(concise) < len(expanded)


def test_hostile_project_never_executes_imports_writes_network_or_subprocess(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "hostile.py").write_text("""import socket,subprocess
from pathlib import Path
Path("IMPORT_WROTE").write_text("bad")
socket.create_connection(("127.0.0.1",9))
subprocess.run(["touch","PROCESS_WROTE"])
@Path("DECORATOR_WROTE").touch()
def f(x=Path("DEFAULT_WROTE").touch()): return x
""")
    (project / "setup.py").write_text('raise RuntimeError("setup executed")')
    before = {p.name: p.read_bytes() for p in project.iterdir()}
    probe = """import sys,os
root=sys.argv[1]
def audit(event,args):
    if event in {"subprocess.Popen","socket.connect","socket.getaddrinfo","os.system"}: raise AssertionError(event)
    if event=="import" and (args[0].split('.')[0] in {"hostile","setup","fastapi","mcp","docker"} or args[0].startswith(("apizr.execution","apizr.oci","apizr.generators"))): raise AssertionError(args[0])
    if event=="exec" and str(args[0].co_filename).startswith(root): raise AssertionError("source execution")
    if event=="open" and isinstance(args[0],str) and args[0].startswith(root) and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC): raise AssertionError("repository write")
sys.addaudithook(audit)
from apizr.repository import scan,catalog_bytes
result=scan(root)
assert len(result.sources)==2
assert not any(name.startswith(("apizr.execution","apizr.oci","apizr.generators","fastapi","mcp")) for name in sys.modules)
sys.stdout.buffer.write(catalog_bytes(result))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(project)],
        cwd=project,
        env={**os.environ, "PATH": "/nonexistent"},
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout)["schema_version"] == "apizr.catalog/v1"
    assert {p.name: p.read_bytes() for p in project.iterdir()} == before

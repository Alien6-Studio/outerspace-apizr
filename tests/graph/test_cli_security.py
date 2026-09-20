import json
import os
import subprocess
import sys

from apizr.cli import main
from apizr.graph import Graph, build_graph, graph_bytes, graph_repository
from apizr.graph.reporting import text_report
from apizr.repository import scan_sources


def test_cli_formats_exit_codes_and_bounded_output(tmp_path, capfd):
    (tmp_path / "a.py").write_text("def f(): return 1\ndef run(): return f()")
    assert main(["graph", str(tmp_path)]) == 0
    assert "Modules: 1" in capfd.readouterr().out
    assert main(["graph", str(tmp_path), "--graph"]) == 0
    canonical = capfd.readouterr().out.encode()
    assert str(tmp_path).encode() not in canonical
    assert main(["graph", str(tmp_path), "--format", "json"]) == 0
    envelope = json.loads(capfd.readouterr().out)
    assert envelope["graph"] == Graph.model_validate_json(canonical).model_dump(
        mode="json"
    )
    assert envelope["statistics"]["relationships"]["calls_capability"] == 1
    assert main(["graph", str(tmp_path), "--max-relationships", "1", "--details"]) == 1
    assert "APIZR-GRAPH-008" in capfd.readouterr().out
    assert main(["graph", str(tmp_path), "--max-calls", "0"]) == 2
    assert "Traceback" not in capfd.readouterr().err
    assert main(["graph", str(tmp_path / "absent")]) == 2
    assert str(tmp_path) not in capfd.readouterr().err
    assert main(["graph", str(tmp_path), "--source-root", ".."]) == 2
    capfd.readouterr()
    (tmp_path / "bad.py").write_text("invalid !")
    assert main(["graph", str(tmp_path)]) == 1
    assert "Catalog has blocking diagnostics" in capfd.readouterr().out
    assert main(["--help"]) == 0
    assert "apizr graph ROOT" in capfd.readouterr().out


def test_report_truncation_and_details():
    files = {f"a{i}.py": b"import lib\ndef f(): return 1" for i in range(25)}
    files.update({f"bad{i}.py": b"invalid !" for i in range(15)})
    catalog = scan_sources(files.items())
    g = build_graph(
        catalog, {s.path: files[s.path] for s in catalog.sources if s.inspection}
    )
    short, long = text_report(g), text_report(g, details=True)
    assert "Further relationships omitted" in short
    assert "Further diagnostics omitted" in short
    assert "omitted;" not in long
    assert len(short) < len(long)


def test_discovery_bytes_shared_despite_file_mutation(monkeypatch, tmp_path):
    import apizr.graph.builder as builder
    import apizr.repository.discovery as discovery

    path = tmp_path / "a.py"
    original = b"def f(): return 1\ndef run(): return f()"
    path.write_bytes(original)
    counts = []
    read_source = discovery.read_source

    def read(*args, **kwargs):
        counts.append(args[2])
        return read_source(*args, **kwargs)

    monkeypatch.setattr(discovery, "read_source", read)
    assemble = builder.assemble

    def mutate(*args, **kwargs):
        catalog = assemble(*args, **kwargs)
        path.write_text('raise RuntimeError("changed after scan")')
        return catalog

    monkeypatch.setattr(builder, "assemble", mutate)
    result = graph_repository(tmp_path)
    assert counts == ["a.py"]
    assert result.graph.capability_calls("python:a:run") == ("python:a:f",)
    assert graph_bytes(result.graph) == graph_bytes(
        build_graph(result.catalog, {"a.py": original})
    )


def test_real_audit_hooks_offline_nonexecution_and_dependency_isolation(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    (root / "hostile.py").write_text("""import socket, subprocess
from pathlib import Path
socket.create_connection(("127.0.0.1",9))
subprocess.run(["touch", "PROCESS_MARKER"])
@Path("DECORATOR_MARKER").touch()
def hostile(x: Path("ANNOTATION_MARKER").touch() = Path("DEFAULT_MARKER").touch()):
 return hostile(x)
""")
    (root / "setup.py").write_text('raise RuntimeError("setup executed")')
    (root / "pyproject.toml").write_text(
        '[build-system]\nbuild-backend="hostile"\nrequires=[]'
    )
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    probe = """import sys,os
root=sys.argv[1]
def audit(event,args):
 if event in {"subprocess.Popen","socket.connect","socket.getaddrinfo","os.system"}: raise AssertionError(event)
 if event=="import" and (args[0].split('.')[0] in {"hostile","setup","fastapi","mcp","docker"} or args[0].startswith(("apizr.execution","apizr.oci","apizr.generators","apizr.governed"))): raise AssertionError(args[0])
 if event=="exec" and str(args[0].co_filename).startswith(root): raise AssertionError("source execution")
 if event=="open" and isinstance(args[0],str) and args[0].startswith(root) and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC): raise AssertionError("repository write")
sys.addaudithook(audit)
from apizr.graph import graph_repository,graph_bytes
import importlib.util
# No resolver is necessary after loading the library itself.
def forbidden(*args,**kwargs): raise AssertionError("installed package resolution")
importlib.util.find_spec=forbidden
result=graph_repository(root)
assert len(result.catalog.sources)==2
assert not any(name.startswith(("apizr.execution","apizr.oci","apizr.generators","apizr.governed","fastapi","mcp")) for name in sys.modules)
sys.stdout.buffer.write(graph_bytes(result.graph))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(root)],
        cwd=root,
        env={**os.environ, "PATH": "/nonexistent"},
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout)["schema_version"] == "apizr.graph/v1"
    assert str(root).encode() not in result.stdout
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before

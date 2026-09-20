import json
import subprocess
import sys

import nbformat
import pytest

from apizr.cli import main


@pytest.mark.parametrize("notebook", [False, True])
def test_modern_cli_generates_python_or_notebook_bundle(tmp_path, capsys, notebook):
    source = tmp_path / ("input.ipynb" if notebook else "input.py")
    text = "def f(x: int) -> int: return x\n"
    if notebook:
        nbformat.write(
            nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(text)]), source
        )
    else:
        source.write_text(text)
    output = tmp_path / "output"
    assert (
        main(
            [
                "generate",
                "rest",
                str(source),
                "--output-dir",
                str(output),
                "--module-name",
                "project.business",
                "--select",
                "f",
            ]
        )
        == 0
    )
    reported = json.loads(capsys.readouterr().out)
    assert reported["schema_version"] == "apizr.rest/v1"
    assert all((output / name).is_file() for name in reported["files"])
    assert (output / "source/project/business.py").exists()
    # Both modern inspection and the existing CLI remain separately routable.
    assert main(["inspect", str(source), "--module-name", "project.business"]) == 0
    assert "Apizr inspection" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("content", "suffix", "extra", "exit_code"),
    [
        ("def f(): yield 1", ".py", [], 1),
        ("not python", ".txt", [], 2),
        ("def bad(:", ".py", [], 2),
        ("not JSON", ".ipynb", [], 2),
        ("def f(): pass", ".py", ["--select", "missing"], 2),
        ("def f(): pass", ".py", ["--select", "f,"], 2),
    ],
)
def test_modern_cli_errors_leave_no_output_and_no_traceback(
    tmp_path, capsys, content, suffix, extra, exit_code
):
    source = tmp_path / ("input" + suffix)
    source.write_text(content)
    output = tmp_path / "output"
    assert (
        main(["generate", "rest", str(source), "--output-dir", str(output), *extra])
        == exit_code
    )
    captured = capsys.readouterr()
    assert "apizr generate rest:" in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()


def test_no_destructive_force_option(tmp_path):
    with pytest.raises(SystemExit) as error:
        main(
            ["generate", "rest", "source.py", "--output-dir", str(tmp_path), "--force"]
        )
    assert error.value.code == 2


def test_core_imports_do_not_load_rest_or_fastapi():
    code = """import sys
from apizr.capabilities import inspect_source
from apizr.readiness import assess
source = b'def f(x: int): return x'
assess(inspect_source(source, module_name='isolated'), source)
assert not any(name == 'fastapi' or name.startswith('fastapi.') or name.startswith('apizr.generators') for name in sys.modules)
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("notebook", [False, True])
def test_fresh_generation_process_has_no_source_import_network_or_subprocess(
    tmp_path, notebook
):
    source = tmp_path / (
        "hostile_rest_target.ipynb" if notebook else "hostile_rest_target.py"
    )
    marker = tmp_path / "executed"
    code = f"""from pathlib import Path
import socket
import subprocess
def f():
    Path({str(marker)!r}).touch()
    socket.create_connection(("127.0.0.1", 9))
    subprocess.run(["false"])
"""
    if notebook:
        nbformat.write(
            nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code)]), source
        )
    else:
        source.write_text(code)
    output = tmp_path / "output"
    probe = """import sys

def guard(event, args):
    if event in {"socket.connect", "subprocess.Popen", "os.system"}:
        raise AssertionError(event)
    if event == "import" and args[0] == "hostile_rest_target":
        raise AssertionError("Target imported during generation")
    if event == "exec" and getattr(args[0], "co_filename", "") == sys.argv[1]:
        raise AssertionError("Target executed during generation")
sys.addaudithook(guard)
from apizr.cli import main
raise SystemExit(main(["generate", "rest", sys.argv[1], "--output-dir", sys.argv[2]]))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(source), str(output)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (output / "app.py").exists()
    assert not marker.exists()

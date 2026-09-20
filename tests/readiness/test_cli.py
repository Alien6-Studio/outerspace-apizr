import json
import subprocess
import sys
from pathlib import Path

import nbformat
import pytest

from apizr.cli import main
from apizr.inspection import inspect_file, inspect_source, json_bytes

ROOT = Path(__file__).resolve().parents[2]


def test_cli_text_json_and_canonical_ir_are_distinct(tmp_path, capsys):
    path = tmp_path / "pricing.py"
    path.write_text("def total(x: int = 1) -> int: return x")
    assert main(["inspect", str(path)]) == 0
    output = capsys.readouterr().out
    assert "Apizr inspection" in output
    assert "readiness: READY" in output
    assert "effects: unknown" in output
    assert "return declaration: int (enforcement: none)" in output
    assert main(["inspect", str(path), "--format", "json"]) == 0
    machine = capsys.readouterr().out
    expected = inspect_source(path.read_bytes(), module_name="pricing")
    assert machine.encode() == json_bytes(expected)
    assert main(["inspect", str(path), "--ir"]) == 0
    ir = capsys.readouterr().out
    assert json.loads(ir) == json.loads(machine)["capability_ir"]
    assert "readiness" not in json.loads(ir)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def f(): pass", 0),
        ("@decorate\ndef f(): pass", 0),
        ("def f(): yield 1", 1),
        ("async def f(): yield 1", 1),
        ("def f(): pass\ndef f(): pass", 1),
        ("def f(x: Callable): pass", 1),
        ("x = 1", 0),
        ("f = lambda: 1", 1),
    ],
)
@pytest.mark.parametrize("flags", [[], ["--format", "json"], ["--ir"]])
def test_exit_codes_are_independent_of_output_mode(
    tmp_path, capsys, source, expected, flags
):
    path = tmp_path / "sample.py"
    path.write_text(source)
    assert main(["inspect", str(path), *flags]) == expected
    output = capsys.readouterr()
    assert output.out and not output.err
    if flags:
        json.loads(output.out)


@pytest.mark.parametrize(
    ("filename", "source"),
    [
        ("invalid.py", "def :"),
        ("bad-name.py", "def f(): pass"),
        ("input.txt", "text"),
        ("broken.ipynb", "not json"),
        ("invalid.ipynb", "[]"),
        ("encoding.py", b"# coding: unknown-encoding\n"),
    ],
)
def test_ordinary_input_errors_have_code_2_and_no_traceback(
    tmp_path, capsys, filename, source
):
    path = tmp_path / filename
    path.write_bytes(source if isinstance(source, bytes) else source.encode())
    assert main(["inspect", str(path)]) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "apizr inspect:" in output.err and "Traceback" not in output.err


def test_missing_file_and_explicit_identity_override(tmp_path, capsys):
    assert main(["inspect", str(tmp_path / "missing.py")]) == 2
    assert "Traceback" not in capsys.readouterr().err
    path = tmp_path / "has spaces.py"
    path.write_text("def f(): pass")
    assert (
        main(
            ["inspect", str(path), "--module-name", "project.valid", "--format", "json"]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["capability_ir"]["capabilities"][0]["id"] == "python:project.valid:f"


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["inspect"],
        ["inspect", "x.py", "--ir", "--format", "json"],
        ["inspect", "x.py", "--format", "yaml"],
    ],
)
def test_argument_errors_exit_2(args, capsys):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_help_preserves_old_options_and_discovers_inspection(capsys):
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "--script" in out and "--notebook" in out and "apizr inspect" in out
    with pytest.raises(SystemExit) as error:
        main(["inspect", "--help"])
    assert error.value.code == 0
    assert "--module-name" in capsys.readouterr().out


def test_notebook_inspection_reuses_ir_adapter_and_separate_digests(tmp_path, capsys):
    path = tmp_path / "pricing.ipynb"
    path.write_bytes((ROOT / "examples/pricing.ipynb").read_bytes())
    assert main(["inspect", str(path), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["capability_ir"]["source"]["kind"] == "notebook"
    assert (
        data["capability_ir"]["source"]["transformed_digest"]
        != data["capability_ir"]["source"]["digest"]
    )
    assert data["readiness"]["source"] == data["capability_ir"]["source"]
    assert inspect_file(path, module_name="pricing").model_dump(mode="json") == data


def test_notebook_magics_are_operational_errors(tmp_path, capsys):
    path = tmp_path / "magic.ipynb"
    nbformat.write(
        nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("%time x")]), path
    )
    assert main(["inspect", str(path)]) == 2
    assert "magics" in capsys.readouterr().err


@pytest.mark.parametrize("kind", ["script", "notebook"])
def test_legacy_console_routing_generates_identical_artifacts(tmp_path, capsys, kind):
    from apizr.main import main as legacy

    source = tmp_path / ("business.py" if kind == "script" else "business.ipynb")
    code = "def value(x: int = 1) -> int: return x\n"
    if kind == "script":
        source.write_text(code)
    else:
        nbformat.write(
            nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code)]), source
        )
    args = [f"--{kind}", str(source), "--force", "--python-version", "3.11"]
    assert main([*args, "--output-dir", str(tmp_path / "new")]) == 0
    capsys.readouterr()
    legacy([*args, "--output-dir", str(tmp_path / "legacy")])
    capsys.readouterr()

    def contents(directory):
        return {
            str(p.relative_to(directory)): p.read_bytes()
            for p in directory.rglob("*")
            if p.is_file()
        }

    assert contents(tmp_path / "new") == contents(tmp_path / "legacy")


def test_python_module_cli_works_outside_checkout(tmp_path):
    path = tmp_path / "simple.py"
    path.write_text("def f(x: int): return x")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "apizr.cli",
            "inspect",
            str(path),
            "--format",
            "json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["readiness"]["assessments"][0][
        "can_generate_interface"
    ]


@pytest.mark.parametrize("notebook", [False, True])
def test_fresh_cli_process_never_imports_target_or_launches_network_subprocess(
    tmp_path, notebook
):
    path = tmp_path / ("hostile_target.ipynb" if notebook else "hostile_target.py")
    marker = tmp_path / "executed"
    code = f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('executed')\ndef f(x: int): return x\n"
    if notebook:
        nbformat.write(
            nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code)]), path
        )
    else:
        path.write_text(code)
    probe = """
import sys

def guard(event, args):
    if event in {'socket.connect', 'subprocess.Popen', 'os.system'}:
        raise AssertionError(event)
    if event == 'import' and args[0] == 'hostile_target':
        raise AssertionError('target imported')
    if event == 'exec' and getattr(args[0], 'co_filename', '') == sys.argv[1]:
        raise AssertionError('target executed')

sys.addaudithook(guard)
from apizr.cli import main
raise SystemExit(main(['inspect', sys.argv[1], '--format', 'json']))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (
        json.loads(result.stdout)["readiness"]["assessments"][0]["state"]
        == "conditional"
    )
    assert not marker.exists()

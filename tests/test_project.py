"""Project files select existing compiler inputs; never execute project content."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from apizr.cli import main
from apizr.compiler import assess_readiness, prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy, plan_bytes
from apizr.project import MAX_PROJECT_BYTES, load_project
from apizr.repository import ScanPolicy
from apizr.repository_readiness import RepositoryReadinessPolicy, report_bytes

EXAMPLE = Path(__file__).parents[1] / "examples/project-config"
VERSION = 'schema_version = "apizr.project/v1"\n'


def project(tmp_path):
    root = tmp_path / "configuration"
    shutil.copytree(EXAMPLE, root)
    return root / "apizr.toml"


def files(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file()
    }


def explicit(path):
    return [
        str(path.parent),
        "--source-root",
        "src",
        "--exclude-dir",
        "ignored",
        "--max-file-bytes",
        "4096",
        "--max-ast-nodes",
        "10000",
    ]


def exposure_flags(path):
    return [
        "--policy",
        str(path.parent / "policies/exposure.json"),
        "--readiness-policy",
        str(path.parent / "policies/readiness.json"),
    ]


def test_python_loader_paths_models_and_compiler(tmp_path, monkeypatch, capfd):
    path = project(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    config = load_project(Path("../configuration/apizr.toml"))
    assert config.root.samefile(path.parent)
    assert config.readiness_policy.samefile(path.parent / "policies/readiness.json")
    assert config.exposure_policy.samefile(path.parent / "policies/exposure.json")
    assert config.scan.source_roots == ("src",)
    assert config.scan.max_file_bytes == 4096
    assert set(ScanPolicy().excluded_directories) < set(
        config.scan.excluded_directories
    )
    readiness = RepositoryReadinessPolicy.model_validate_json(
        config.readiness_policy.read_bytes()
    )
    exposure = ExposurePolicy.model_validate_json(config.exposure_policy.read_bytes())
    report = assess_readiness(
        config.root,
        scan_policy=config.scan,
        graph_policy=config.graph,
        readiness_policy=readiness,
    )
    prepared = prepare_exposure(
        config.root,
        policy=exposure,
        scan_policy=config.scan,
        graph_policy=config.graph,
        readiness_policy=readiness,
    )
    assert report_bytes(report) == report_bytes(prepared.readiness)
    assert prepared.plan.capability_ids() == ("python:calculator:add",)
    assert render_bundle(prepared, interface="rest")[
        "exposure-plan.json"
    ] == plan_bytes(prepared.plan)
    assert capfd.readouterr() == ("", "")


@pytest.mark.parametrize("operation", ["readiness", "plan", "rest", "mcp"])
def test_project_and_explicit_commands_have_identical_bytes(
    tmp_path, monkeypatch, capfd, operation
):
    path = project(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    if operation == "readiness":
        configured = ["readiness", "--project", str(path), "--report"]
        direct = [
            "readiness",
            *explicit(path),
            "--policy",
            str(path.parent / "policies/readiness.json"),
            "--report",
        ]
    elif operation == "plan":
        configured = ["expose", "plan", "--project", str(path), "--plan"]
        direct = ["expose", "plan", *explicit(path), *exposure_flags(path), "--plan"]
    else:
        configured = [
            "expose",
            "build",
            operation,
            "--project",
            str(path),
            "--output-dir",
            "configured",
        ]
        direct = [
            "expose",
            "build",
            operation,
            *explicit(path),
            *exposure_flags(path),
            "--output-dir",
            "explicit",
        ]
    assert main(configured) == 0
    actual = capfd.readouterr()
    assert main(direct) == 0
    assert capfd.readouterr() == actual
    if operation in ("rest", "mcp"):
        assert files(elsewhere / "configured") == files(elsewhere / "explicit")
        assert not (path.parent / "configured").exists()  # Output remains CWD-relative.


@pytest.mark.parametrize(
    "section,field,flag,value,default",
    [
        ("scan", "max_file_bytes", "--max-file-bytes", 1, 1048576),
        ("scan", "max_source_files", "--max-source-files", 1, 1000),
        ("scan", "max_total_bytes", "--max-total-bytes", 1, 16777216),
        ("scan", "max_entries", "--max-entries", 1, 20000),
        ("scan", "max_depth", "--max-depth", 1, 64),
        ("graph", "max_ast_nodes", "--max-ast-nodes", 1, 500000),
        ("graph", "max_relationships", "--max-relationships", 1, 50000),
        ("graph", "max_calls", "--max-calls", 1, 50000),
        ("graph", "max_imports", "--max-imports", 1, 10000),
    ],
)
def test_file_bounds_survive_parser_defaults_and_explicit_defaults_override(
    tmp_path, capfd, section, field, flag, value, default
):
    root = tmp_path / "src"
    root.mkdir()
    (root / "a.py").write_text(
        "import math\nimport sys\ndef a(): return math.floor(1)\ndef b(): return a()\n"
    )
    (root / "b.py").write_text("def c(): return 1\n")
    nested = root / "nested/deeper"
    nested.mkdir(parents=True)
    (nested / "c.py").write_text("def d(): return 2\n")
    path = tmp_path / "apizr.toml"
    path.write_text(VERSION + f'root = "src"\n[{section}]\n{field} = {value}\n')
    assert main(["readiness", "--project", str(path), "--report"]) == 1
    limited = capfd.readouterr().out
    assert main(["readiness", str(root), flag, str(value), "--report"]) == 1
    assert capfd.readouterr().out == limited
    assert (
        main(["readiness", "--project", str(path), flag, str(default), "--report"]) == 0
    )
    restored = capfd.readouterr().out
    assert restored != limited
    assert main(["readiness", str(root), "--report"]) == 0
    assert capfd.readouterr().out == restored


def test_cli_root_source_roots_and_exclusions(tmp_path, monkeypatch, capfd):
    path = project(tmp_path)
    other = tmp_path / "other"
    (other / "code").mkdir(parents=True)
    (other / "code/calculator.py").write_text("def add(a: int) -> int: return a\n")
    for excluded in ("ignored", "extra", ".venv"):
        (other / f"code/{excluded}").mkdir()
        (other / f"code/{excluded}/invalid.py").write_text("invalid syntax !!!")
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "expose",
                "plan",
                "other",
                "--project",
                str(path),
                "--source-root",
                "code",
                "--exclude-dir",
                "extra",
                "--plan",
            ]
        )
        == 0
    )
    actual = capfd.readouterr().out
    assert (
        main(
            [
                "expose",
                "plan",
                "other",
                "--source-root",
                "code",
                "--exclude-dir",
                "ignored",
                "--exclude-dir",
                "extra",
                "--max-file-bytes",
                "4096",
                "--max-ast-nodes",
                "10000",
                *exposure_flags(path),
                "--plan",
            ]
        )
        == 0
    )
    assert capfd.readouterr().out == actual


def test_cli_policy_paths_replace_project_paths_and_stay_cwd_relative(
    tmp_path, monkeypatch, capfd
):
    path = project(tmp_path)
    # Overridden project policy paths need not exist or contain valid JSON.
    (path.parent / "policies/readiness.json").unlink()
    (path.parent / "policies/exposure.json").write_text("invalid JSON")
    readiness = {"execution": {"modes": ["direct"]}}
    exposure = {
        "interfaces": ["mcp"],
        "execution": {"allowed": ["direct"]},
        "selection": {"include": ["python:calculator:add"]},
    }
    (tmp_path / "readiness.json").write_text(json.dumps(readiness))
    (tmp_path / "exposure.json").write_text(json.dumps(exposure))
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "readiness",
                "--project",
                str(path),
                "--policy",
                "readiness.json",
                "--report",
            ]
        )
        == 0
    )
    capfd.readouterr()
    assert (
        main(
            [
                "expose",
                "plan",
                "--project",
                str(path),
                "--readiness-policy",
                "readiness.json",
                "--policy",
                "exposure.json",
                "--plan",
            ]
        )
        == 0
    )
    result = json.loads(capfd.readouterr().out)
    assert result["capabilities"]
    assert (
        main(
            [
                "expose",
                "build",
                "rest",
                "--project",
                str(path),
                "--readiness-policy",
                "readiness.json",
                "--policy",
                "exposure.json",
                "--output-dir",
                "out",
            ]
        )
        == 1
    )
    assert not (
        tmp_path / "out"
    ).exists()  # Replaced policy did not retain REST permission.


@pytest.mark.parametrize(
    "flags",
    [
        ["--select", "python:calculator:add"],
        ["--exclude", "python:calculator:add"],
        ["--all-ready"],
        ["--allow-conditional"],
        ["--interface", "rest"],
        ["--execution-mode", "direct"],
        ["--require-control", "wall_timeout"],
    ],
)
def test_project_policy_conflicts_with_inline_choices(tmp_path, capfd, flags):
    path = project(tmp_path)
    assert main(["expose", "plan", "--project", str(path), *flags]) == 2
    output = capfd.readouterr()
    assert not output.out and "invalid/inaccessible policy" in output.err


def test_no_exposure_policy_allows_inline_choices_without_merging_readiness(
    tmp_path, capfd
):
    path = project(tmp_path)
    path.write_text(
        path.read_text().replace('exposure_policy = "policies/exposure.json"\n', "")
    )
    args = [
        "expose",
        "plan",
        "--project",
        str(path),
        "--interface",
        "rest",
        "--select",
        "python:calculator:add",
    ]
    assert main([*args, "--execution-mode", "local-process"]) == 1
    capfd.readouterr()
    assert main([*args, "--execution-mode", "direct", "--plan"]) == 0
    assert "python:calculator:add" in capfd.readouterr().out


@pytest.mark.parametrize(
    "body",
    [
        "",
        'schema_version = "apizr.project/v2"',
        "schema_version = 1",
        VERSION + "root = 3",
        VERSION + "root = true",
        VERSION + 'root = ""',
        VERSION + 'root = "https://example.com/repo"',
        VERSION + 'root = "git:repo"',
        VERSION + "readiness_policy = []",
        VERSION + 'exposure_policy = "https://example.com/policy"',
        VERSION + 'root = "\\u0000"',
        VERSION + "root = 2026-09-23",
        VERSION + "[unknown]\nx = 1",
        VERSION + 'plugin = "evil"',
        VERSION + 'execution_policy = "execution.json"',
        VERSION + 'output_dir = "out"',
        VERSION + "publish = true",
        VERSION + "[scan]\nunknown = 1",
        VERSION + "[graph]\nunknown = 1",
        VERSION + '[scan]\nmax_file_bytes = "4096"',
        VERSION + "[scan]\nmax_file_bytes = 1.0",
        VERSION + "[scan]\nmax_depth = true",
        VERSION + '[graph]\nmax_calls = "10"',
        VERSION + "[graph]\nmax_imports = false",
        VERSION + "[graph]\nmax_ast_nodes = 0",
        VERSION + '[scan]\nsource_roots = "src"',
        VERSION + "[scan]\nsource_roots = [1]",
        VERSION + '[scan]\nsource_roots = [".."]',
        VERSION + '[scan]\nexcluded_directories = ["a/b"]',
        VERSION + '[scan]\nincluded_suffixes = [".ipynb"]',
        VERSION + '[scan]\nsymlinks = "follow"',
        VERSION + '[graph]\nschema_version = "unknown"',
        VERSION + "root = [",
        VERSION + 'root = "."\nroot = "."',
    ],
)
def test_unknown_versions_fields_types_and_invalid_toml(tmp_path, capfd, body):
    path = tmp_path / "apizr.toml"
    path.write_text(body)
    with pytest.raises(ValueError):
        load_project(path)
    assert main(["readiness", "--project", str(path)]) == 2
    captured = capfd.readouterr()
    assert not captured.out and "Traceback" not in captured.err


@pytest.mark.parametrize("mode", ["missing", "directory", "utf8", "oversized"])
def test_inaccessible_invalid_and_oversized_files(tmp_path, capfd, mode):
    path = tmp_path / "apizr.toml"
    if mode == "directory":
        path.mkdir()
    elif mode == "utf8":
        path.write_bytes(b"\xff")
    elif mode == "oversized":
        path.write_text(VERSION + "#" + "x" * MAX_PROJECT_BYTES)
    with pytest.raises((OSError, ValueError)):
        load_project(path)
    for args in (
        ["readiness"],
        ["expose", "plan"],
        ["expose", "build", "rest", "--output-dir", str(tmp_path / "out")],
    ):
        assert main([*args, "--project", str(path)]) == 2
        assert not capfd.readouterr().out
    assert not (tmp_path / "out").exists()


def test_size_limit_and_minimal_defaults(tmp_path):
    path = tmp_path / "apizr.toml"
    path.write_text(VERSION + "#" + "x" * (MAX_PROJECT_BYTES - len(VERSION) - 1))
    config = load_project(path)
    assert config.root == tmp_path
    assert config.readiness_policy is config.exposure_policy is None
    assert config.scan == ScanPolicy()
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(ValueError, match="size limit"):
        load_project(path)


def test_only_explicit_project_is_loaded_and_no_project_root_is_still_required(
    tmp_path, monkeypatch, capfd
):
    (tmp_path / "apizr.toml").write_text("BROKEN TOML")
    (tmp_path / "sample.py").write_text("def f(): return 1\n")
    monkeypatch.chdir(tmp_path)
    assert main(["readiness", ".", "--report"]) == 0
    capfd.readouterr()
    for args in (["readiness"], ["expose", "plan"]):
        with pytest.raises(SystemExit) as error:
            main(args)
        assert error.value.code == 2
        assert "required: root" in capfd.readouterr().err


def test_absent_selected_policy_and_invalid_policy_are_errors(tmp_path, capfd):
    path = project(tmp_path)
    policy = path.parent / "policies/readiness.json"
    policy.unlink()
    assert main(["readiness", "--project", str(path)]) == 2
    capfd.readouterr()
    policy.write_text("{}")
    (path.parent / "policies/exposure.json").write_text('{"unknown":"secret"}')
    assert main(["expose", "plan", "--project", str(path)]) == 2
    assert "secret" not in capfd.readouterr().err


def test_project_file_cannot_satisfy_required_output_argument(tmp_path):
    path = project(tmp_path)
    with pytest.raises(SystemExit) as error:
        main(["expose", "build", "rest", "--project", str(path)])
    assert error.value.code == 2


def test_loading_is_python_only_and_commands_do_not_execute_or_download(tmp_path):
    path = project(tmp_path)
    (path.parent / "src/hostile.py").write_text(
        'import socket, subprocess\nopen("MARKER", "w").write("executed")\nsocket.create_connection(("localhost", 9))\nsubprocess.run(["git", "clone", "remote"])\n'
    )
    probe = """import os, sys, importlib.metadata
from pathlib import Path
path = Path(sys.argv[1])
root = str(path.parent / "src")
def audit(event, args):
    if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "socket.connect", "socket.bind", "socket.getaddrinfo"}:
        raise AssertionError(event)
    if event == "import" and (args[0].split(".")[0] in {"calculator", "hostile", "fastapi", "mcp", "nbconvert", "IPython", "black", "questionary", "docker"} or args[0].startswith("apizr.extensions.plugins")):
        raise AssertionError(args[0])
    if event == "exec" and str(args[0].co_filename).startswith(root):
        raise AssertionError("project execution")
def forbidden(*args, **kwargs): raise AssertionError("plugin discovery")
sys.addaudithook(audit)
importlib.metadata.entry_points = forbidden
from apizr.project import load_project
assert load_project(path).scan.source_roots == ("src",)
assert not any(name == "apizr.cli" or name.endswith("_cli") for name in sys.modules)
from apizr.cli import main
assert main(["readiness", "--project", str(path), "--report"]) in (0, 1)
assert main(["expose", "plan", "--project", str(path), "--plan"]) == 0
for interface in ("rest", "mcp"):
    assert main(["expose", "build", interface, "--project", str(path), "--output-dir", interface]) == 0
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(path)],
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
    assert not (tmp_path / "MARKER").exists()


def test_absolute_paths_and_literal_environment_names(tmp_path, monkeypatch):
    path = project(tmp_path)
    path.write_text(
        VERSION
        + f"root = {json.dumps(str(path.parent))}\n"
        + f"readiness_policy = {json.dumps(str(path.parent / 'policies/readiness.json'))}\n"
        + 'exposure_policy = "$POLICY.json"\n'
    )
    monkeypatch.setenv("POLICY", "unexpected")
    config = load_project(path)
    assert config.root == path.parent
    assert config.readiness_policy == path.parent / "policies/readiness.json"
    assert config.exposure_policy == path.parent / "$POLICY.json"


def test_legacy_yaml_configuration_ignores_project_file(tmp_path, monkeypatch, capfd):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "apizr.toml").write_text("INVALID PROJECT FILE")
    (tmp_path / "sample.py").write_text("def f(x: int) -> int: return x + 1\n")
    (tmp_path / "config.yaml").write_text(
        "dockerizr:\n  server:\n    port: 5017\n    workers: 2\n"
    )
    assert (
        main(
            [
                "--script",
                "sample.py",
                "--configuration",
                "config.yaml",
                "--output-dir",
                "legacy",
            ]
        )
        == 0
    )
    result = json.loads(capfd.readouterr().out)
    assert "Dockerfile" in result["files"]
    assert "--port 5017 --workers 2" in (tmp_path / "legacy/start.sh").read_text()

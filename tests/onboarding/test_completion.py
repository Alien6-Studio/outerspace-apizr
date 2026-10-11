"""One captured grammar, drift detection, bounded backend and actual shell adapters."""

import ast
import importlib.util
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from apizr import cli
from apizr.cli.completion import FILES, candidates, main, script
from apizr.cli.completion_spec import COMMANDS

ROOT = Path(__file__).resolve().parents[2]


def test_completion_covers_actual_parsers_and_dispatch():
    spec = importlib.util.spec_from_file_location(
        "completion_model", ROOT / "scripts/completion_model.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.capture() == COMMANDS
    source = ast.parse(Path(cli.__file__).read_text())
    commands = set()
    for node in ast.walk(source):
        if isinstance(node, ast.Compare) and ast.unparse(node.left) == "arguments[0]":
            for right in node.comparators:
                commands.update(
                    c.value
                    for c in ast.walk(right)
                    if isinstance(c, ast.Constant) and isinstance(c.value, str)
                )
    assert commands - {"__complete"} == set(COMMANDS["commands"])


@pytest.mark.parametrize(
    "words,expected",
    [
        (["experiment", ""], ("diff", "expose", "inspect", "list", "run", "show")),
        (["experiment", "expose", "RUN", "--interface", ""], ("mcp", "rest")),
        (["experiment", "expose", "RUN", "--root", ""], (FILES,)),
        (["experiment", "expose", "RUN", "--output-dir", ""], (FILES,)),
        (["experiment", "expose", "RUN", "--capability", ""], ()),
        (["experiment", "expose", "RUN", "--artifact", ""], ()),
        (["experiment", "expose", "RUN", "--dependency", ""], ()),
        (["experiment", "diff", "a" * 64, "b" * 64, "--format", ""], ("json", "text")),
        (["experiment", "diff", "--store", ""], (FILES,)),
        (["experiment", "diff", ""], ()),
        (["experiment", "run", ""], (FILES,)),
        (["experiment", "run", "--store", ""], (FILES,)),
        (["experiment", "list", "--status", ""], ("cancelled", "failed", "success")),
        (["experiment", "show", "--format", ""], ("json", "text")),
        (["experiment", "inspect", ""], (FILES,)),
        (["experiment", "inspect", "train.py", "--format", ""], ("json", "text")),
        (["experiment", "inspect", "--root", ""], (FILES,)),
        (["clients", "export", "--format", ""], ("bruno", "insomnia", "postman")),
        (["clients", "sync", "--format", "p"], ("postman",)),
        (["clients", "export", "--format=br"], ("--format=bruno",)),
        (["expose", "build", ""], ("mcp", "rest")),
        (["doctor", "--profile", ""], ("clients", "core", "delivery", "mcp", "oci")),
        (["completion", ""], ("bash", "fish", "zsh")),
        (["generate", ""], ("mcp", "rest")),
        (["delivery", ""], ("resume", "run")),
        (["init", "--source-root", ""], (FILES,)),
        (["inspect", ""], (FILES,)),
        (["inspect", "--", "-source"], (FILES,)),
        (
            ["doctor", "--project", "private.toml", "--profile", ""],
            ("clients", "core", "delivery", "mcp", "oci"),
        ),
        (["clients", "export", "--bogus", ""], ()),
        (["doctor", "--unknown="], ()),
        (["clients", "bogus", ""], ()),
        (["doctor", "--profile", "mcp", ""], ()),
        (["completion", "zsh", "extra", ""], ()),
        (["plugins", "enable", ""], ()),
        (["init", "--source-root", "\n"], ()),
        (["a"] * 129, ()),
        (["x" * 2049], ()),
    ],
)
def test_candidates(words, expected):
    assert candidates(words) == expected


def test_options_and_prefixes():
    assert "--operator-policy" in candidates(["doctor", "--"])
    assert candidates(["doc"]) == ("doctor",)
    assert "--source-root" in candidates(["init", "--s"])
    assert "--version" in candidates(["--"])
    assert candidates(["doctor", "--json", "--p"]) == (
        "--plugins-dir",
        "--profile",
        "--project",
    )


def test_no_dynamic_access(monkeypatch, capsys):
    def forbidden(*a, **k):
        pytest.fail("completion touched dynamic state")

    monkeypatch.setenv("APIZR_SECRET", "SENTINEL_MUST_NOT_APPEAR")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr(os, "listdir", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    for shell in ("bash", "zsh", "fish"):
        assert script(shell) == script(shell)
        assert "SENTINEL" not in script(shell)
        assert str(Path.home()) not in script(shell)
        assert main([shell]) == 0
    assert main(["--", "doctor", "--profile", ""], backend=True) == 0
    assert cli.main(["__complete", "--", "clients", "export", "--format", ""]) == 0
    assert cli.main(["completion", "bash"]) == 0
    assert "SENTINEL" not in capsys.readouterr().out
    with pytest.raises(ValueError, match="completion_shell_invalid"):
        script("powershell")


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
@pytest.mark.parametrize(
    "journey", ["clients export", "experiment diff A B", "experiment expose RUN"]
)
def test_real_shell_syntax_and_candidates(tmp_path, shell, journey):
    executable = shutil.which(shell)
    if executable is None:
        # The dedicated Linux qualification requires all three binaries.
        assert not os.environ.get("APIZR_REQUIRE_SHELLS"), f"{shell} required"
        assert "apizr __complete" in script(shell)
        return
    path = tmp_path / f"apizr.{shell}"
    path.write_text(script(shell))
    subprocess.run([executable, "-n", str(path)], check=True, capture_output=True)
    if shell == "bash":
        command = 'source "$1"; COMP_WORDS=(apizr clients export --format ""); COMP_CWORD=4; _apizr_complete; printf "%s\\n" "${COMPREPLY[@]}"'
    elif shell == "zsh":
        command = 'compdef() { :; }; compadd() { shift; print -l -- "$@"; }; source "$1"; words=(apizr clients export --format ""); CURRENT=5; _apizr'
    else:
        command = 'source $argv[1]; complete -C "apizr clients export --format "'
    command = command.replace("clients export", journey)
    count = len(journey.split())
    command = command.replace("COMP_CWORD=4", f"COMP_CWORD={count + 2}").replace(
        "CURRENT=5", f"CURRENT={count + 3}"
    )
    if journey == "experiment expose RUN":
        command = command.replace("--format", "--interface")
    argv = [
        executable,
        *(
            {"bash": ["--noprofile", "--norc"], "zsh": ["-f"], "fish": ["--no-config"]}[
                shell
            ]
        ),
        "-c",
        command,
        *([str(path)] if shell == "fish" else ["test", str(path)]),
    ]
    result = subprocess.run(argv, capture_output=True, text=True, check=True)
    expected = (
        {"mcp", "rest"}
        if journey == "experiment expose RUN"
        else {"json", "text"}
        if journey.startswith("experiment")
        else {"postman", "bruno", "insomnia"}
    )
    assert {line.split("\t")[0] for line in result.stdout.splitlines()} == expected, (
        result
    )

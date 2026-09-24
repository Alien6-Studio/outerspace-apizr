import json
import os
import signal
import subprocess
import sys
import time

import pytest

from apizr.cli import main

pytestmark = pytest.mark.timeout(25)


@pytest.fixture
def policies(tmp_path):
    exposure = tmp_path / "exposure.json"
    exposure.write_text(
        json.dumps(
            {
                "interfaces": ["rest", "mcp"],
                "execution": {"allowed": ["direct"]},
                "selection": {"include": ["python:calculator:add"]},
            }
        )
    )
    readiness = tmp_path / "readiness.json"
    readiness.write_text('{"execution":{"modes":["direct"]}}')
    return ["--policy", str(exposure), "--readiness-policy", str(readiness)]


@pytest.mark.parametrize(
    "command",
    [
        ["readiness", "--report"],
        ["expose", "plan", "--plan"],
        ["expose", "build", "rest"],
        ["expose", "build", "mcp"],
    ],
)
@pytest.mark.parametrize("subdir,source_root", [("service", None), (".", "service")])
def test_remote_and_local_exact_parity(
    remote, trust_cli, scratch, policies, tmp_path, capfd, command, subdir, source_root
):
    url, source, commit = remote
    flags = policies if command[0] == "expose" else []
    if source_root:
        flags = [*flags, "--source-root", source_root]
    build = "build" in command
    output = tmp_path / "local"
    expected_code = main(
        [
            *command,
            str(source / subdir),
            *flags,
            *(["--output-dir", str(output)] if build else []),
        ]
    )
    expected = capfd.readouterr()
    actual_output = tmp_path / "remote"
    actual_code = main(
        [
            *command,
            "--git",
            url,
            "--ref",
            commit,
            "--subdir",
            subdir,
            *flags,
            *(["--output-dir", str(actual_output)] if build else []),
        ]
    )
    actual = capfd.readouterr()
    assert actual_code == expected_code == 0
    assert actual.out == expected.out
    assert actual.err == f"Git snapshot: commit {commit}\n"
    assert not list(scratch.iterdir())
    if build:
        assert {
            p.relative_to(output): p.read_bytes()
            for p in output.rglob("*")
            if p.is_file()
        } == {
            p.relative_to(actual_output): p.read_bytes()
            for p in actual_output.rglob("*")
            if p.is_file()
        }
    else:
        json.loads(actual.out)


@pytest.mark.parametrize(
    "options",
    [
        ["--git", "https://example.com/a"],
        ["--git", "https://example.com/a", "--ref", "main", "."],
        ["--git", "https://example.com/a", "--ref", "main", "--project", "absent.toml"],
        [".", "--ref", "main"],
        [".", "--subdir", "x"],
    ],
)
@pytest.mark.parametrize(
    "command",
    [
        ["readiness"],
        ["expose", "plan"],
        ["expose", "build", "rest", "--output-dir", "unused"],
        ["expose", "build", "mcp", "--output-dir", "unused"],
    ],
)
def test_ambiguous_input_rejected_before_acquisition(command, options, monkeypatch):
    monkeypatch.setattr(
        "apizr.git_source_cli.acquire_snapshot",
        lambda *a, **k: pytest.fail("acquisition started"),
    )
    with pytest.raises(SystemExit) as error:
        main([*command, *options])
    assert error.value.code == 2


def test_remote_refusal_retains_exit_code(remote, trust_cli, scratch, policies, capfd):
    # Explicit exposure still cannot widen default readiness to direct mode.
    assert (
        main(
            [
                "expose",
                "plan",
                "--git",
                remote[0],
                "--ref",
                "main",
                "--subdir",
                "service",
                *policies[:2],
            ]
        )
        == 1
    )
    result = capfd.readouterr()
    assert not result.out and "execution" in result.err
    assert "git_acquisition_failed" not in result.err


@pytest.mark.parametrize(
    "command",
    [
        ["readiness"],
        ["expose", "plan", "--interface", "rest", "--execution-mode", "direct"],
    ],
)
def test_cli_fixed_git_errors(command, capfd):
    assert (
        main([*command, "--git", "https://user:SECRET@example.com/a", "--ref", "main"])
        == 2
    )
    result = capfd.readouterr()
    assert not result.out
    assert "git_invalid_url" in result.err and "SECRET" not in result.err


@pytest.mark.parametrize(
    "command",
    [
        ["readiness"],
        ["expose", "plan", "--interface", "rest", "--execution-mode", "direct"],
    ],
)
def test_cli_interrupt_is_clean(command, tmp_path, scratch, remote, tls):
    from apizr.git_source import acquire_snapshot

    wrapper = tmp_path / "bin"
    wrapper.mkdir()
    ready = tmp_path / "started"
    executable = wrapper / "git"
    executable.write_text(
        f"#!{sys.executable}\nimport os,time\nopen({str(ready)!r},'w').write(str(os.getpid()))\ntime.sleep(30)\n"
    )
    executable.chmod(0o700)
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            "from apizr.cli import main; import sys; sys.exit(main(sys.argv[1:]))",
            *command,
            "--git",
            "https://example.com/a",
            "--ref",
            "main",
        ],
        env={**os.environ, "PATH": str(wrapper), "TMPDIR": str(scratch)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 5
        while (
            not ready.exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert ready.exists()
        process.send_signal(signal.SIGINT)
        out, error = process.communicate(timeout=5)
        assert process.returncode == 130
        assert not out and b"git_cancelled" in error and b"Traceback" not in error
        pid = int(ready.read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        assert not list(scratch.iterdir())
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=3)
        for stream in (process.stdout, process.stderr):
            stream.close()
    with acquire_snapshot(remote[0], "main", ca_file=tls[0]):
        pass

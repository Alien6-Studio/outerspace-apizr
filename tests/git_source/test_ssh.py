import json
import os
import shutil
import socket
import subprocess
from pathlib import Path
from threading import Event, Thread

import pytest

from apizr.cli import main
from apizr.compiler import assess_readiness, prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy
from apizr.git_source import AcquisitionLimits, GitSourceError, acquire_snapshot
from apizr.git_source.ssh import configure_ssh, validate_ssh_url
from apizr.repository_readiness import RepositoryReadinessPolicy

from .conftest import git_fixture, ssh_fixture
from .test_cli import policies  # noqa: F401

pytestmark = pytest.mark.timeout(30)


def options(remote):
    return {"ssh_agent_socket": remote.socket, "ssh_known_hosts": remote.known_hosts}


def success(remote):
    with acquire_snapshot(remote.url, "main", **options(remote)) as result:
        assert result.commit == remote.commit


@pytest.mark.parametrize("ref", ["main", "v1", "annotated", "commit"])
def test_authenticated_snapshot(ssh_remote, scratch, ref):
    remote = ssh_remote
    known = remote.known_hosts.read_bytes()
    with acquire_snapshot(
        remote.url,
        remote.commit if ref == "commit" else ref,
        subdir="service",
        **options(remote),
    ) as snapshot:
        assert snapshot.commit == remote.commit
        assert (
            snapshot.root.joinpath("calculator.py").read_bytes()
            == (remote.source / "service/calculator.py").read_bytes()
        )
        assert {p.name for p in snapshot.root.iterdir()} == {"calculator.py"}
    assert not snapshot.root.exists()
    assert remote.known_hosts.read_bytes() == known


@pytest.mark.parametrize(
    "url",
    [
        "git@example.org:org/repo.git",
        "git@example.org:/srv/org/repo.git",
        "ssh://git@example.org:2222/org/repo.git",
        "ssh://git@[::1]:2222/org/repo.git",
    ],
)
def test_ssh_address_forms(url):
    validate_ssh_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "ssh://host/repo",
        "ssh://user:password@host/repo",
        "git@-ohost:repo",
        "ssh://-ouser@host/repo",
        "ssh://user@host:0/repo",
        "ssh://user@host:65536/repo",
        "ssh://user@host/repo?secret=1",
        "ssh://user@host/repo#secret",
        "ssh://user@host/repo%0a",
        "git@host:repo;touch-pwned",
        "git@host:$(touch-pwned)",
        "git@host:`id`",
        "git@host:-option",
        "git@host:../repo",
        "ssh://user@host/a//repo",
        "ssh://user@host/a/../repo",
        "ssh://user@host/a\nb",
        "ssh://user@host/a\\b",
        "ssh://user@host/" + "a" * 4096,
    ],
)
def test_injection_rejected_before_process(url, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *a: pytest.fail("process lookup"))
    with pytest.raises(GitSourceError, match="git_invalid_url"):
        with acquire_snapshot(
            url, "main", ssh_agent_socket=Path("a"), ssh_known_hosts=Path("b")
        ):
            pytest.fail("accepted")


@pytest.mark.parametrize("source", ["https://example.org/repo", "."])
@pytest.mark.parametrize(
    "command",
    [
        ["readiness"],
        ["expose", "plan"],
        ["expose", "build", "rest"],
        ["expose", "build", "mcp"],
    ],
)
def test_cli_ssh_options_only_with_ssh(source, command, monkeypatch):
    monkeypatch.setattr(
        "apizr.git_source_cli.acquire_snapshot",
        lambda *a, **k: pytest.fail("acquisition"),
    )
    root = [source] if source == "." else ["--git", source, "--ref", "main"]
    with pytest.raises(SystemExit) as caught:
        main(
            [
                *command,
                *root,
                "--ssh-agent-socket",
                "agent",
                "--ssh-known-hosts",
                "known",
            ]
        )
    assert caught.value.code == 2


@pytest.mark.parametrize(
    "provided", [[], ["--ssh-agent-socket", "a"], ["--ssh-known-hosts", "b"]]
)
def test_cli_requires_both_ssh_options(provided):
    with pytest.raises(SystemExit) as caught:
        main(["readiness", "--git", "git@host:repo", "--ref", "main", *provided])
    assert caught.value.code == 2


def test_api_transport_options():
    for kwargs, url, code in [
        ({}, "git@host:repo", "git_ssh_options_required"),
        (
            {"ssh_agent_socket": Path("a")},
            "https://host/repo",
            "git_ssh_options_unsupported",
        ),
        (
            {
                "ssh_agent_socket": Path("a"),
                "ssh_known_hosts": Path("b"),
                "ca_file": Path("c"),
            },
            "git@host:repo",
            "git_ssh_ca_unsupported",
        ),
    ]:
        with pytest.raises(GitSourceError, match=code):
            with acquire_snapshot(url, "main", **kwargs):
                pytest.fail("accepted")


@pytest.mark.parametrize(
    "failure",
    [
        "absent",
        "loop",
        "regular",
        "empty",
        "wrong",
        "access",
        "unknown",
        "changed",
        "revoked",
    ],
)
def test_authentication_refusals_clean_and_recover(
    ssh_remote, scratch, tmp_path, monkeypatch, failure
):
    remote = ssh_remote
    kwargs = options(remote)
    url = remote.url
    known = remote.known_hosts.read_bytes()
    monkeypatch.setenv("SSH_AUTH_SOCK", str(remote.socket))
    with ssh_fixture.agent(tmp_path, None) as empty:
        if failure == "absent":
            kwargs["ssh_agent_socket"] = tmp_path / "absent"
        elif failure == "loop":
            loop = tmp_path / "agent-loop"
            loop.symlink_to(loop)
            kwargs["ssh_agent_socket"] = loop
        elif failure == "regular":
            kwargs["ssh_agent_socket"] = remote.known_hosts
        elif failure in ("empty", "wrong"):
            kwargs["ssh_agent_socket"] = empty
            if failure == "wrong":
                ssh_fixture.key(tmp_path / "wrong")
                subprocess.run(
                    ["ssh-add", str(tmp_path / "wrong")],
                    env={"SSH_AUTH_SOCK": str(empty)},
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
        elif failure == "access":
            url += "-absent"
        else:
            alternate = tmp_path / "known"
            if failure == "unknown":
                alternate.write_text("")
            elif failure == "changed":
                ssh_fixture.key(tmp_path / "wrong-host")
                alternate.write_bytes(
                    known.split(b" ", 1)[0]
                    + b" "
                    + (tmp_path / "wrong-host.pub").read_bytes()
                )
            else:
                alternate.write_bytes(b"@revoked " + known)
            kwargs["ssh_known_hosts"] = alternate
        with pytest.raises(GitSourceError) as caught:
            with acquire_snapshot(url, "main", **kwargs):
                pytest.fail("accepted")
        assert str(caught.value) in {"git_ssh_agent_unavailable", "git_command_failed"}
    assert remote.known_hosts.read_bytes() == known
    assert not list(scratch.iterdir())
    success(remote)


@pytest.mark.parametrize("failure", ["missing", "directory", "fifo", "large", "ssh"])
def test_ssh_prerequisites(ssh_remote, tmp_path, monkeypatch, scratch, failure):
    remote = ssh_remote
    kwargs = options(remote)
    bad = tmp_path / "bad"
    if failure == "directory":
        bad.mkdir()
    elif failure == "fifo":
        os.mkfifo(bad)
    elif failure == "large":
        bad.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    if failure == "ssh":
        original = shutil.which
        monkeypatch.setattr(
            "shutil.which", lambda name: None if name == "ssh" else original(name)
        )
    else:
        kwargs["ssh_known_hosts"] = bad
    with pytest.raises(
        GitSourceError, match="git_ssh_(known_hosts_(unavailable|limit)|not_found)"
    ):
        with acquire_snapshot(remote.url, "main", **kwargs):
            pytest.fail("accepted")


@pytest.mark.parametrize(
    "command",
    [
        ["readiness", "--report"],
        ["expose", "plan", "--plan"],
        ["expose", "build", "rest"],
        ["expose", "build", "mcp"],
    ],
)
def test_cli_exact_parity(ssh_remote, policies, scratch, tmp_path, capfd, command):  # noqa: F811
    remote = ssh_remote
    flags = policies if command[0] == "expose" else []
    build = "build" in command
    local, target = tmp_path / "local", tmp_path / "remote"
    assert (
        main(
            [
                *command,
                str(remote.source / "service"),
                *flags,
                *(["--output-dir", str(local)] if build else []),
            ]
        )
        == 0
    )
    expected = capfd.readouterr()
    assert (
        main(
            [
                *command,
                "--git",
                remote.url,
                "--ref",
                remote.commit,
                "--subdir",
                "service",
                "--ssh-agent-socket",
                str(remote.socket),
                "--ssh-known-hosts",
                str(remote.known_hosts),
                *flags,
                *(["--output-dir", str(target)] if build else []),
            ]
        )
        == 0
    )
    actual = capfd.readouterr()
    assert actual.out == expected.out
    assert actual.err == f"Git snapshot: commit {remote.commit}\n"
    if build:

        def files(root):
            return {
                p.relative_to(root): p.read_bytes()
                for p in root.rglob("*")
                if p.is_file()
            }

        assert files(local) == files(target)
        for name, data in files(target).items():
            assert not any(
                part in {".git", ".ssh", "known_hosts", "ssh-known-hosts"}
                for part in name.parts
            )
            assert (
                b"PRIVATE KEY" not in data and str(remote.socket).encode() not in data
            )
    else:
        json.loads(actual.out)


def test_ssh_configuration_is_isolated(ssh_remote, tmp_path, monkeypatch, scratch):
    remote = ssh_remote
    marker = tmp_path / "executed"
    evil = tmp_path / "evil"
    evil.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
    evil.chmod(0o700)
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh/config").write_text(
        f'Match exec "{evil}"\nHost *\n ProxyCommand {evil}\n LocalCommand {evil}\n PermitLocalCommand yes\n'
    )
    for name, value in {
        "HOME": str(home),
        "GIT_SSH": str(evil),
        "GIT_SSH_COMMAND": str(evil),
        "GIT_SSH_VARIANT": "plink",
        "SSH_AUTH_SOCK": "absent",
        "SSH_ASKPASS": str(evil),
        "SECRET": "should-not-propagate",
    }.items():
        monkeypatch.setenv(name, value)
    (remote.source / "danger.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    )
    git_fixture.git(remote.source, "add", ".")
    git_fixture.git(remote.source, "commit", "-m", "static only")
    with acquire_snapshot(remote.url, "main", **options(remote)) as snapshot:
        assess_readiness(snapshot.root)
    assert not marker.exists()
    # Inspect OpenSSH's own expanded configuration, not merely our argv.
    work = tmp_path / "work"
    work.mkdir()
    environment = configure_ssh(work, remote.socket, remote.known_hosts)
    argv = json.loads((work / "ssh-argv.json").read_text())
    expanded = subprocess.check_output(
        [*argv, "-G", "example.org"],
        cwd=work,
        env={"PATH": os.defpath, **environment},
        text=True,
        timeout=5,
    )
    for expected in [
        "identityfile none",
        "certificatefile none",
        "batchmode yes",
        "stricthostkeychecking true",
        "forwardagent no",
        "controlmaster false",
        "passwordauthentication no",
        "globalknownhostsfile /dev/null",
        "userknownhostsfile ./ssh-known-hosts",
    ]:
        assert expected in expanded
    assert not marker.exists()


def test_retained_sources_after_ssh_cleanup(ssh_remote, scratch):
    remote = ssh_remote
    policy = ExposurePolicy.model_validate(
        {
            "interfaces": ["rest", "mcp"],
            "execution": {"allowed": ["direct"]},
            "selection": {"include_all_ready": True},
        }
    )
    readiness = RepositoryReadinessPolicy.model_validate(
        {"execution": {"modes": ["direct"]}}
    )
    local = prepare_exposure(
        remote.source / "service", policy=policy, readiness_policy=readiness
    )
    with acquire_snapshot(
        remote.url, "main", subdir="service", **options(remote)
    ) as snapshot:
        prepared = prepare_exposure(
            snapshot.root, policy=policy, readiness_policy=readiness
        )
    assert not snapshot.root.exists()
    for interface in ("rest", "mcp"):
        assert render_bundle(prepared, interface=interface) == render_bundle(
            local, interface=interface
        )


@pytest.mark.parametrize("kind", ["timeout", "cancel"])
def test_stalled_ssh_is_bounded_and_next_acquisition_works(
    ssh_remote, scratch, monkeypatch, kind
):
    remote = ssh_remote
    accepted = Event()
    disconnected = Event()
    cancel = Event()
    processes = []
    original_popen = subprocess.Popen

    def capture(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", capture)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(5)

        def stall():
            with listener.accept()[0] as connection:
                connection.settimeout(5)
                accepted.set()
                while connection.recv(4096):
                    pass
                disconnected.set()

        thread = Thread(target=stall)
        thread.start()

        def interrupt():
            assert accepted.wait(5)
            cancel.set()

        interrupter = Thread(target=interrupt) if kind == "cancel" else None
        if interrupter:
            interrupter.start()
        try:
            with pytest.raises(
                GitSourceError,
                match=f"git_{'cancelled' if kind == 'cancel' else 'timeout'}",
            ):
                with acquire_snapshot(
                    f"ssh://fixture@127.0.0.1:{listener.getsockname()[1]}/repo",
                    "main",
                    **options(remote),
                    cancel=cancel,
                    limits=AcquisitionLimits(
                        total_timeout_ms=500 if kind == "timeout" else 3000
                    ),
                ):
                    pytest.fail("accepted")
        finally:
            thread.join(timeout=5)
            if interrupter:
                interrupter.join(timeout=5)
        assert not thread.is_alive() and disconnected.is_set()
    assert processes
    for process in processes:
        assert process.poll() is not None
        assert process.stdout.closed and process.stderr.closed
    assert not list(scratch.iterdir())
    success(remote)


def test_scp_address_with_real_ssh(ssh_remote, tmp_path, monkeypatch, scratch):
    import sys
    from urllib.parse import urlsplit

    remote = ssh_remote
    parsed = urlsplit(remote.url)
    actual_ssh = shutil.which("ssh")
    wrapper = tmp_path / "ssh-port-wrapper"
    # Test-only port translation permits SCP's default-port syntax without
    # binding privileged port 22 or touching the machine's SSH service.
    wrapper.write_text(
        f"#!{sys.executable}\nimport os,sys\nos.execv({actual_ssh!r}, [{actual_ssh!r}, '-p', {str(parsed.port)!r}, *sys.argv[1:]])\n"
    )
    wrapper.chmod(0o700)
    original = shutil.which
    monkeypatch.setattr(
        "shutil.which", lambda name: str(wrapper) if name == "ssh" else original(name)
    )
    with acquire_snapshot(
        f"{parsed.username}@127.0.0.1:{remote.source}", "main", **options(remote)
    ) as snapshot:
        assert snapshot.commit == remote.commit


def test_ssh_paths_are_literal_data(ssh_remote, tmp_path, scratch):
    remote = ssh_remote
    # Spaces, token syntax and shell punctuation must not become SSH config or
    # local shell syntax. The explicit file remains unmodified.
    known = tmp_path / 'known %h ${HOME} " ; hosts'
    known.write_bytes(remote.known_hosts.read_bytes())
    agent_link = tmp_path / 'agent %h ${HOME} " ; socket'
    agent_link.symlink_to(remote.socket)
    with acquire_snapshot(
        remote.url, "main", ssh_agent_socket=agent_link, ssh_known_hosts=known
    ) as result:
        assert result.commit == remote.commit
    assert known.read_bytes() == remote.known_hosts.read_bytes()


def test_cli_sigint_during_ssh_handshake(ssh_remote, scratch):
    import signal
    import sys

    remote = ssh_remote
    accepted, disconnected = Event(), Event()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(5)

        def serve():
            with listener.accept()[0] as connection:
                connection.settimeout(5)
                accepted.set()
                while connection.recv(4096):
                    pass
                disconnected.set()

        thread = Thread(target=serve)
        thread.start()
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-c",
                "import sys; from apizr.cli import main; sys.exit(main(sys.argv[1:]))",
                "readiness",
                "--git",
                f"ssh://fixture@127.0.0.1:{listener.getsockname()[1]}/repo",
                "--ref",
                "main",
                "--ssh-agent-socket",
                str(remote.socket),
                "--ssh-known-hosts",
                str(remote.known_hosts),
                "--report",
            ],
            env={**os.environ, "TMPDIR": str(scratch)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            assert accepted.wait(5)
            process.send_signal(signal.SIGINT)
            out, error = process.communicate(timeout=5)
            assert process.returncode == 130
            assert not out and b"git_cancelled" in error and b"Traceback" not in error
            assert str(remote.socket).encode() not in error
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
            process.stdout.close()
            process.stderr.close()
            thread.join(timeout=5)
        assert not thread.is_alive() and disconnected.is_set()
    assert not list(scratch.iterdir())
    success(remote)

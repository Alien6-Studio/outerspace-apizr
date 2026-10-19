"""The qualification guard must detect real network attempts and restore its venv."""

import json
import subprocess
import venv

import pytest

from scripts.qualification.interfaces.python_network_guard import guarded_engine


def test_isolated_children_are_guarded_and_the_environment_is_restored(tmp_path):
    environment = tmp_path / "engine"
    venv.EnvBuilder(with_pip=False).create(environment)
    python = environment / "bin/python"
    log = tmp_path / "network.log"
    with guarded_engine(python, log) as result:
        subprocess.run([str(python), "-I", "-B", "-c", "print('offline')"], check=True)
    assert result == {
        "positive_controls": 2,
        "connection_attempts": 0,
        "guarded_processes": 1,
        "apizr_processes": 0,
    }
    assert not list(environment.rglob("_apizr_qualification_network_*"))
    with pytest.raises(AssertionError, match="attempted Python network"):
        with guarded_engine(python, tmp_path / "refused.log"):
            child = subprocess.run(
                [
                    str(python),
                    "-I",
                    "-B",
                    "-c",
                    "import socket;socket.getaddrinfo('127.0.0.1',1)",
                ],
                capture_output=True,
            )
            assert (
                child.returncode != 0
                and b"qualification_network_denied" in child.stderr
            )
    assert not list(environment.rglob("_apizr_qualification_network_*"))
    with pytest.raises(RuntimeError, match="business"):
        with guarded_engine(python, tmp_path / "failed.log"):
            raise RuntimeError("business")
    assert not list(environment.rglob("_apizr_qualification_network_*"))
    rows = [
        json.loads(line) for line in (tmp_path / "refused.log").read_text().splitlines()
    ]
    assert any(row["kind"] == "attempt" for row in rows)

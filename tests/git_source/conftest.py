import importlib.util
import sys
from pathlib import Path

import pytest


def load(name):
    path = Path(__file__).resolve().parents[2] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


https = load("https_fixture")
git_fixture = load("git_https_fixture")


@pytest.fixture(scope="module")
def tls(tmp_path_factory):
    return https.certificate(tmp_path_factory.mktemp("git-cert"))


@pytest.fixture
def remote(tmp_path, tls):
    source, commit = git_fixture.repository(tmp_path)
    with https.https_server(*tls, git_fixture.handler(tmp_path)) as url:
        yield f"{url}/repo.git", source, commit


@pytest.fixture
def trust_cli(tmp_path, tls, monkeypatch):
    wrapper = git_fixture.trusted_git(tmp_path / "bin", tls[0])
    monkeypatch.setenv("PATH", str(wrapper))


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    import tempfile

    directory = tmp_path / "acquisition"
    directory.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(directory))
    yield directory
    assert not list(directory.iterdir())


ssh_fixture = load("git_ssh_fixture")


@pytest.fixture
def ssh_remote(tmp_path):
    with ssh_fixture.server(tmp_path / "ssh") as remote:
        yield remote

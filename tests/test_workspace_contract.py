"""Project declarations and private sessions preserve distinct authority boundaries."""

import json
import os
import tempfile

import pytest
from analysis_authorization import analysis_policy
from pydantic import ValidationError

from apizr.workspace.analysis_session import Scope, load_scope, read_session
from apizr.workspace.mcp_session import read_session as read_mcp_session
from apizr.workspace.operator_policy import AuthorizationDenied
from apizr.workspace.project import ProjectConfig, load_project


def configured_scope(root):
    path = root / "apizr.toml"
    path.write_text(
        'schema_version = "apizr.project/v1"\n'
        'readiness_policy = "readiness.json"\n'
        'exposure_policy = "exposure.json"\n'
        "[scan]\nmax_file_bytes = 4096\n"
    )
    (root / "readiness.json").write_text('{"execution":{"modes":["direct"]}}')
    (root / "exposure.json").write_text(
        '{"interfaces":["rest"],"execution":{"allowed":["direct"]}}'
    )
    return load_scope(path, analysis_policy(root))


def test_project_contract_has_no_operator_or_output_authority():
    assert ProjectConfig.model_json_schema()["additionalProperties"] is False
    for key in ("operator_policy", "grants", "execution", "output", "delivery"):
        with pytest.raises(ValidationError):
            ProjectConfig.model_validate(
                {"schema_version": "apizr.project/v1", key: {}}
            )


def test_loading_project_does_not_read_policies_or_authorize_analysis(tmp_path):
    path = tmp_path / "apizr.toml"
    path.write_text(
        'schema_version = "apizr.project/v1"\nreadiness_policy = "missing.json"\n'
    )
    assert load_project(path).readiness_policy == tmp_path / "missing.json"
    with pytest.raises(AuthorizationDenied):
        load_scope(path)


@pytest.mark.parametrize("reader", [read_session, read_mcp_session])
def test_session_owns_settings_and_consumes_its_descriptor(tmp_path, reader):
    scope = configured_scope(tmp_path)
    serialized = scope.model_dump_json()
    for name in ("apizr.toml", "readiness.json", "exposure.json"):
        (tmp_path / name).unlink()
    with tempfile.TemporaryFile() as stream:
        stream.write(serialized.encode())
        stream.seek(0)
        descriptor = os.dup(stream.fileno())
        received = reader(descriptor)
        actual = received if isinstance(received, Scope) else received.analysis
        assert actual == scope
        assert actual.scan.max_file_bytes == 4096
        with pytest.raises(OSError):
            os.fstat(descriptor)


@pytest.mark.parametrize("reader", [read_session, read_mcp_session])
def test_session_rejects_duplicate_authority_before_source_access(
    tmp_path, monkeypatch, reader
):
    from apizr.workspace import analysis_session

    scope = configured_scope(tmp_path)
    raw = scope.model_dump_json().replace('"root":', '"root":"/other", "root":', 1)

    def unexpected(*args):
        pytest.fail("Ambiguous authority reached source admission")

    monkeypatch.setattr(analysis_session, "open_analysis_root", unexpected)
    with tempfile.TemporaryFile() as stream:
        stream.write(raw.encode())
        stream.seek(0)
        with pytest.raises(ValueError):
            reader(os.dup(stream.fileno()))


@pytest.mark.parametrize(
    "update", [{"root": "relative"}, {"device": -1}, {"inode": -1}]
)
def test_session_contract_validates_the_pinned_source(tmp_path, update):
    scope = configured_scope(tmp_path)
    with pytest.raises(ValidationError):
        Scope.model_validate_json(
            json.dumps({**scope.model_dump(), **update}), strict=True
        )


@pytest.mark.parametrize("reader", [read_session, read_mcp_session])
def test_captured_inode_never_authorizes_a_replaced_root(tmp_path, reader):
    root = tmp_path / "project"
    root.mkdir()
    scope = configured_scope(root)
    root.rename(tmp_path / "previous")
    root.mkdir()
    with tempfile.TemporaryFile() as stream:
        stream.write(scope.model_dump_json().encode())
        stream.seek(0)
        with pytest.raises(AuthorizationDenied):
            reader(os.dup(stream.fileno()))

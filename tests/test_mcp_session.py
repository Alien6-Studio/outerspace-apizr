"""Operator-only delivery loading is bounded, frozen and never reopened by MCP."""

import json
import os
import tempfile
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from analysis_authorization import analysis_policy
from batch_inputs import request

from apizr import mcp_cli
from apizr.analysis_session import load_scope
from apizr.mcp_session import (
    DeliverySession,
    McpSession,
    read_session,
)


@pytest.mark.parametrize(
    "fault",
    [
        "relative",
        "symlink",
        "ancestor",
        "fifo",
        "directory",
        "oversized",
        "duplicate",
        "malformed",
        "extra",
        "wrong_build",
        "duplicate_destination",
    ],
)
def test_request_loader_refuses_before_plugin_admission(
    tmp_path, monkeypatch, capsys, fault
):
    project = tmp_path / "apizr.toml"
    project.write_text('schema_version="apizr.project/v1"\nroot="."\n')
    policy = tmp_path / "operator.json"
    policy.write_text(analysis_policy(tmp_path).model_dump_json())
    batch = request(tmp_path)
    file = tmp_path / "delivery.json"
    file.write_text(batch.model_dump_json(by_alias=True))
    if fault == "relative":
        file = Path("delivery.json")
    elif fault in {"symlink", "ancestor"}:
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path if fault == "ancestor" else file)
        file = alias / file.name if fault == "ancestor" else alias
    elif fault in {"fifo", "directory"}:
        file.unlink()
        os.mkfifo(file) if fault == "fifo" else file.mkdir()
    elif fault == "oversized":
        file.write_bytes(b"x" * 524289)
    else:
        data = json.loads(file.read_text())
        if fault == "extra":
            data["unknown"] = "PRIVATE"
        if fault == "wrong_build":
            data["destinations"][0]["push"]["image_id"] = "sha256:" + "f" * 64
        if fault == "duplicate_destination":
            data["destinations"].append(data["destinations"][0])
        file.write_text(json.dumps(data))
        if fault == "duplicate":
            file.write_text(
                file.read_text().replace(
                    '"evidence_root":', '"evidence_root":"/PRIVATE", "evidence_root":'
                )
            )
        if fault == "malformed":
            file.write_text('{"PRIVATE":')
    monkeypatch.setattr(
        mcp_cli, "_admitted_mcp", lambda *a: pytest.fail("plugin admission")
    )
    assert (
        mcp_cli.main(
            [
                "serve",
                "--project",
                str(project),
                "--operator-policy",
                str(policy),
                "--delivery-request",
                str(file),
            ]
        )
        == 2
    )
    out = capsys.readouterr()
    assert out.out == "" and "PRIVATE" not in out.err and str(tmp_path) not in out.err
    assert not Path(batch.evidence_root).exists()


def test_policy_is_required_before_any_loading(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mcp_cli, "load_scope", lambda *a: pytest.fail("scope load"))
    assert (
        mcp_cli.main(
            [
                "serve",
                "--project",
                str(tmp_path / "apizr.toml"),
                "--delivery-request",
                str(tmp_path / "request"),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err == "apizr mcp: delivery_policy_required\n"


def test_launcher_captures_request_policy_and_selected_store_once(
    tmp_path, monkeypatch
):
    project = tmp_path / "apizr.toml"
    project.write_text('schema_version="apizr.project/v1"\nroot="."\n')
    authority = analysis_policy(tmp_path)
    policy = tmp_path / "operator.json"
    policy.write_text(authority.model_dump_json())
    batch = request(tmp_path)
    file = tmp_path / "delivery.json"
    file.write_text(batch.model_dump_json(by_alias=True))
    store = tmp_path / "plugins"
    user = tmp_path / "user.toml"
    user.write_text('schema_version="apizr.user/v1"\nplugins_dir="plugins"\n')
    admitted = []
    record = SimpleNamespace(python="/private/python", module="apizr_mcp")
    monkeypatch.setattr(
        mcp_cli,
        "_admitted_mcp",
        lambda directory: admitted.append(directory) or nullcontext((record, 42)),
    )

    class Executed(Exception):
        pass

    def execute(program, args, environment):
        assert environment == {}
        assert (
            "--delivery-request" not in args
            and str(file) not in args
            and str(policy) not in args
        )
        file.write_text("PRIVATE changed request")
        policy.write_text("PRIVATE changed authority")
        captured = read_session(os.dup(int(args[args.index("--session-fd") + 1])))
        assert captured.delivery.request == batch
        assert captured.delivery.plugins_dir == str(store)
        assert captured.analysis.operator_policy == authority
        assert "delivery" not in type(captured.analysis).model_fields
        with pytest.raises(ValueError):
            captured.delivery.plugins_dir = "/other"
        raise Executed

    monkeypatch.setattr(mcp_cli.os, "execve", execute)
    with pytest.raises(Executed):
        mcp_cli.main(
            [
                "serve",
                "--project",
                str(project),
                "--operator-policy",
                str(policy),
                "--delivery-request",
                str(file),
                "--user-config",
                str(user),
            ]
        )
    assert admitted == [store]
    assert not store.exists() and not Path(batch.evidence_root).exists()


@pytest.mark.parametrize("fault", ["invalid", "oversized", "duplicate", "policy"])
def test_private_session_refuses_malformed_authority(tmp_path, fault):
    project = tmp_path / "apizr.toml"
    project.write_text('schema_version="apizr.project/v1"\nroot="."\n')
    scope = load_scope(project, analysis_policy(tmp_path))
    session = McpSession(
        analysis=scope,
        delivery=DeliverySession(
            request=request(tmp_path), plugins_dir=str(tmp_path / "plugins")
        ),
    )
    raw = session.model_dump_json(by_alias=True)
    if fault == "invalid":
        raw = "{}"
    if fault == "oversized":
        raw = "x" * 1048577
    if fault == "duplicate":
        raw = raw.replace('"plugins_dir":', '"plugins_dir":"/PRIVATE", "plugins_dir":')
    if fault == "policy":
        data = json.loads(raw)
        data["analysis"]["operator_policy"] = None
        raw = json.dumps(data)
    with tempfile.TemporaryFile() as stream:
        stream.write(raw.encode())
        stream.seek(0)
        with pytest.raises(ValueError):
            read_session(os.dup(stream.fileno()))

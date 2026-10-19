"""Consent, bounded counters and observation failures at the real CLI/SDK boundary."""

import json
import os
import stat
import sys
import threading
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest

from apizr import telemetry, tracking
from apizr.cli.commands import telemetry as adapter
from apizr.telemetry import collection, consent


@pytest.fixture
def env(tmp_path, monkeypatch):
    value = {"APIZR_TELEMETRY_CONFIG": str(tmp_path / "preferences/consent.json")}
    monkeypatch.setenv("APIZR_TELEMETRY_CONFIG", value["APIZR_TELEMETRY_CONFIG"])
    for key in (
        "CI",
        "APIZR_TELEMETRY_ALLOWED",
        "APIZR_TELEMETRY",
        "APIZR_TELEMETRY_PREVIEW",
        "APIZR_SERVED_PROCESS",
        "APIZR_EXPERIMENT_RUNNER",
    ):
        monkeypatch.delenv(key, raising=False)
    return value


def test_explicit_boolean_consent_precedence_and_no_event_spool(env, tmp_path):
    assert telemetry.status(environ=env).enabled is False
    assert not Path(env["APIZR_TELEMETRY_CONFIG"]).exists()
    assert telemetry.enable(environ=env).enabled is True
    config = Path(env["APIZR_TELEMETRY_CONFIG"])
    assert json.loads(config.read_bytes()) == {
        "schema_version": "apizr.telemetry-consent/v1",
        "enabled": True,
    }
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert telemetry.status(environ={**env, "APIZR_TELEMETRY": "0"}).enabled is False
    assert telemetry.status(environ={**env, "CI": "true"}).enabled is False
    assert (
        telemetry.status(environ={**env, "APIZR_TELEMETRY_ALLOWED": "0"}).enabled
        is False
    )
    assert telemetry.disable(environ={**env, "APIZR_TELEMETRY": "1"}).enabled is False
    assert telemetry.status(environ={**env, "APIZR_TELEMETRY": "1"}).enabled is False
    assert list(config.parent.iterdir()) == [config]


@pytest.mark.parametrize(
    "content",
    [
        b"[]",
        b"{}",
        b"not json",
        b"\xff",
        b"x" * 513,
        b'{"schema_version":"apizr.telemetry-consent/v2","enabled":true}',
        b'{"schema_version":"apizr.telemetry-consent/v1","enabled":"true"}',
        b'{"schema_version":"apizr.telemetry-consent/v1","enabled":true,"source":"secret"}',
        b'{"schema_version":"apizr.telemetry-consent/v1","enabled":false,"enabled":true}',
    ],
)
def test_invalid_consent_fails_closed_without_echo(env, content):
    path = Path(env["APIZR_TELEMETRY_CONFIG"])
    path.parent.mkdir()
    path.write_bytes(content)
    state = telemetry.status(environ={**env, "APIZR_TELEMETRY": "1"})
    assert state.enabled is False
    assert state.reason == "invalid_preferences"


@pytest.mark.parametrize(
    "kind", ["symlink", "directory", "fifo", "growing", "replaced", "changed_kind"]
)
def test_preferences_require_a_bounded_regular_file(env, tmp_path, kind, monkeypatch):
    path = Path(env["APIZR_TELEMETRY_CONFIG"])
    path.parent.mkdir()
    if kind == "symlink":
        target = tmp_path / "target"
        target.write_text(
            '{"schema_version":"apizr.telemetry-consent/v1","enabled":true}'
        )
        path.symlink_to(target)
        with pytest.raises(ValueError, match="invalid_telemetry_config"):
            telemetry.enable(environ=env)
    elif kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.write_bytes(b"x" * (513 if kind == "growing" else 10))
        original = path.stat()
        monkeypatch.setattr(
            consent.os,
            "fstat",
            lambda fd: SimpleNamespace(
                st_mode=stat.S_IFDIR if kind == "changed_kind" else stat.S_IFREG,
                st_size=1,
                st_dev=original.st_dev,
                st_ino=original.st_ino + (1 if kind == "replaced" else 0),
            ),
        )
    assert (
        telemetry.status(environ={**env, "APIZR_TELEMETRY": "1"}).reason
        == "invalid_preferences"
    )


def test_preference_byte_boundary_and_disabled_context_does_not_read(env, monkeypatch):
    path = Path(env["APIZR_TELEMETRY_CONFIG"])
    path.parent.mkdir()
    raw = b'{"schema_version":"apizr.telemetry-consent/v1","enabled":true}'
    path.write_bytes(raw + b" " * (512 - len(raw)))
    assert telemetry.status(environ=env).enabled is True

    def forbidden(path):
        raise AssertionError("disabled context read preferences")

    monkeypatch.setattr(consent, "_read", forbidden)
    for restriction in (
        {"CI": "1"},
        {"APIZR_TELEMETRY_ALLOWED": "0"},
        {"APIZR_TELEMETRY": "0"},
        {"APIZR_SERVED_PROCESS": "1"},
        {"APIZR_EXPERIMENT_RUNNER": "1"},
    ):
        assert telemetry.status(environ={**env, **restriction}).enabled is False


@pytest.mark.parametrize(
    "platform,directory",
    [
        ("darwin", "Library/Application Support/Apizr"),
        ("linux", ".config/apizr"),
        ("win32", "AppData/Roaming/Apizr"),
    ],
)
def test_platform_preferences_are_operator_owned(
    platform, directory, tmp_path, monkeypatch
):
    monkeypatch.setattr(consent.sys, "platform", platform)
    monkeypatch.setattr(consent.Path, "home", lambda: tmp_path)
    assert consent.preference_path({}) == tmp_path / directory / "telemetry.json"
    assert consent.preference_path(
        {"APPDATA": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path)}
    ) == (
        tmp_path / "Apizr/telemetry.json"
        if platform == "win32"
        else tmp_path / "apizr/telemetry.json"
        if platform == "linux"
        else tmp_path / directory / "telemetry.json"
    )


@pytest.mark.parametrize("value", ["relative.json", "/private/tmp/../consent.json"])
def test_relative_and_traversing_preference_locations_refused(value):
    env = {"APIZR_TELEMETRY_CONFIG": value, "APIZR_TELEMETRY": "1"}
    assert not telemetry.status(environ=env).enabled
    with pytest.raises(ValueError, match="invalid_telemetry_config"):
        telemetry.enable(environ=env)


def test_failed_preference_write_cleans_temporary_state(env, monkeypatch):
    def refused(*args):
        raise OSError("private path")

    monkeypatch.setattr(consent.os, "replace", refused)
    with pytest.raises(ValueError, match="^invalid_telemetry_config$"):
        telemetry.enable(environ=env)
    assert list(Path(env["APIZR_TELEMETRY_CONFIG"]).parent.iterdir()) == []


def test_enable_never_overwrites_an_unrelated_file_or_persists_ci_consent(env):
    path = Path(env["APIZR_TELEMETRY_CONFIG"])
    path.parent.mkdir()
    path.write_bytes(b"scientific evidence, not consent")
    with pytest.raises(ValueError, match="invalid_telemetry_config"):
        telemetry.enable(environ=env)
    assert path.read_bytes() == b"scientific evidence, not consent"
    path.unlink()
    for guard in (
        {"CI": "true"},
        {"APIZR_SERVED_PROCESS": "1"},
        {"APIZR_EXPERIMENT_RUNNER": "1"},
        {"APIZR_TELEMETRY_ALLOWED": "0"},
    ):
        assert telemetry.enable(environ={**env, **guard}).enabled is False
        assert not path.exists()


def test_bounded_memory_and_disable_discard_all_scopes(env):
    enabled = {**env, "APIZR_TELEMETRY": "1"}
    with telemetry.capture(environ=enabled) as usage:
        for _ in range(1005):
            collection.observe("inspect", "success")
        assert usage._total == 1000
        data = json.loads(usage.preview()["payload"])
        assert data["events"] == [
            {"operation": "inspect", "outcome": "success", "count": 1000}
        ]
        telemetry.disable(environ=env)
        assert usage._counts == {}
        assert json.loads(usage.preview()["payload"])["events"] == []
    assert json.loads(usage.preview()["payload"])["events"] == []
    usage.record("inspect", "success")
    assert usage._counts == {}


def test_only_closed_events_and_owner_thread_are_observed(env):
    with telemetry.capture(environ={**env, "APIZR_TELEMETRY": "1"}) as usage:
        for operation, outcome in (
            ("source.py", "success"),
            ("inspect", "private traceback"),
            (object(), "success"),
            ("inspect", object()),
        ):
            usage.record(operation, outcome)
        thread = threading.Thread(target=usage.record, args=("inspect", "success"))
        thread.start()
        thread.join()
        assert usage._counts == {}
        usage.record("inspect", "refused")
        assert (
            json.loads(usage.preview()["payload"])["events"][0]["outcome"] == "refused"
        )


def test_live_scope_budget_does_not_accumulate_unbounded_registry(env):
    with ExitStack() as stack:
        captures = [
            stack.enter_context(telemetry.capture(environ=env)) for _ in range(40)
        ]
        assert len(collection._LIVE) == 32
        captures[0].__enter__()
    assert not collection._LIVE
    captures[-1].__enter__()
    assert not collection._LIVE


def test_collection_and_preview_failure_do_not_change_computation(
    env, monkeypatch, capsys
):
    def failed(*args, **kwargs):
        raise RuntimeError("private detail")

    with telemetry.capture(environ={**env, "APIZR_TELEMETRY": "1"}) as usage:
        monkeypatch.setattr(collection, "decision", failed)
        collection.observe("inspect", "success")
        assert usage._counts == {}
        monkeypatch.setattr(usage, "record", failed)
        collection.observe("inspect", "success")
        usage.environ = {"APIZR_TELEMETRY_PREVIEW": "1"}
        monkeypatch.setattr(usage, "preview", failed)
        collection.emit_preview(usage)
        assert capsys.readouterr() == ("", "")


def test_sdk_records_only_coarse_capture_outcome_separately(env, tmp_path, monkeypatch):
    with telemetry.capture(environ={**env, "APIZR_TELEMETRY": "1"}) as usage:
        with tracking.session(root=tmp_path) as session:
            tracking.log_parameter("PRIVATE_PARAMETER", "PRIVATE_VALUE")
            tracking.log_metric("PRIVATE_METRIC", 0.75)
        payload = usage.preview()["payload"]
        assert json.loads(payload)["events"] == [
            {"operation": "capture_session", "outcome": "success", "count": 1}
        ]
        assert "PRIVATE" not in payload and "run_digest" not in payload
        assert "telemetry" not in session.record.model_dump_json()
    failure = RuntimeError("preserved business error")
    monkeypatch.setattr(
        collection,
        "observe",
        lambda *args: (_ for _ in ()).throw(RuntimeError("collection failure")),
    )
    with pytest.raises(RuntimeError) as observed:
        with tracking.session(root=tmp_path):
            raise failure
    assert observed.value is failure


def test_cli_control_status_and_immediate_disable(env, capsys):
    assert adapter.main(["enable"]) == 0
    assert json.loads(capsys.readouterr().out)["collection_enabled"] is True
    assert adapter.main(["status"]) == 0
    assert "payload" not in json.loads(capsys.readouterr().out)
    assert adapter.main(["disable"]) == 0
    assert json.loads(capsys.readouterr().out)["collection_enabled"] is False
    assert adapter.main(["preview"]) == 0
    assert json.loads(json.loads(capsys.readouterr().out)["payload"])["events"] == []


@pytest.mark.parametrize(
    "argv,outcome,code",
    [
        (["inspect", "private.py"], "success", 0),
        (["experiment", "inspect", "private.ipynb"], "refused", 2),
        (["experiment", "show", "private"], "failed", 1),
        (["experiment", "list"], "success", 0),
        (["experiment", "diff", "a", "b"], "success", 0),
        (["generate", "rest"], "success", 0),
        (["generate", "mcp"], "refused", 2),
    ],
)
def test_cli_exact_local_preview_does_not_change_exit_code(
    env, monkeypatch, capsys, argv, outcome, code
):
    monkeypatch.setenv("APIZR_TELEMETRY", "1")
    monkeypatch.setenv("APIZR_TELEMETRY_PREVIEW", "1")
    assert adapter.run_command(argv, lambda: code) == code
    report = json.loads(
        capsys.readouterr().err.removeprefix("APIZR_TELEMETRY_PREVIEW ")
    )
    payload = json.loads(report["payload"])
    assert payload["events"][0]["outcome"] == outcome
    assert "private" not in report["payload"]
    assert report["transmission_available"] is False


def test_cli_failed_observation_enter_exit_and_business_identity(env, monkeypatch):
    def failed(*args, **kwargs):
        raise RuntimeError("collector failure")

    monkeypatch.setattr(adapter, "capture", failed)
    calls = []
    assert adapter.run_command(["inspect"], lambda: calls.append(1) or 0) == 0
    assert calls == [1]
    error = RuntimeError("business")
    with pytest.raises(RuntimeError) as result:
        adapter.run_command([], lambda: (_ for _ in ()).throw(error))
    assert result.value is error


def test_cli_system_exit_and_finalization_failure_are_preserved(env, monkeypatch):
    class Collector:
        environ = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            raise RuntimeError()

    monkeypatch.setattr(adapter, "capture", lambda **kwargs: Collector())
    monkeypatch.setattr(
        adapter, "observe", lambda *args: (_ for _ in ()).throw(RuntimeError())
    )
    for code in (0, 2):
        with pytest.raises(SystemExit) as result:
            adapter.run_command(["inspect"], lambda code=code: sys.exit(code))
        assert result.value.code == code


def test_lazy_exports_unknown_name():
    with pytest.raises(AttributeError):
        _ = telemetry.not_an_api

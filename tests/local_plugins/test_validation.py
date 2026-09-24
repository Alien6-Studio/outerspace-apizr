"""Reject unsupported artifacts before installing, and fail closed on local state."""

import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from apizr.local_plugins import (
    Inventory,
    PluginError,
    backend,
    install_extension,
    list_extensions,
    store,
)
from apizr.local_plugins import wheel as wheel_module

pytestmark = pytest.mark.timeout(20)


@pytest.mark.parametrize(
    "options,code",
    [
        ({"manifest_changes": {"protocol": "apizr.extension/v99"}}, "invalid_manifest"),
        ({"manifest_changes": {"schema": "v99"}}, "invalid_manifest"),
        ({"manifest_changes": {"extra": True}}, "invalid_manifest"),
        ({"manifest_changes": {"name": "UPPER"}}, "invalid_manifest"),
        ({"manifest_changes": {"module": "../unsafe"}}, "invalid_manifest"),
        ({"manifest_changes": {"module": "missing"}}, "missing_entry_module"),
        ({"manifest_changes": {"version": "2.0"}}, "inconsistent_metadata"),
        ({"manifest_changes": {"name": "other"}}, "inconsistent_metadata"),
        ({"manifest_raw": b"not-json"}, "invalid_manifest"),
        ({"manifest_raw": b'{"name":"x","name":"y"}'}, "invalid_manifest"),
        ({"metadata_extra": "Requires-Dist: requests\n"}, "dependencies_not_supported"),
        (
            {"metadata_extra": 'Requires-Dist: requests; extra == "unused"\n'},
            "dependencies_not_supported",
        ),
        ({"metadata_extra": "Name: duplicate\n"}, "invalid_wheel"),
        ({"filename": "other-1.0-py3-none-any.whl"}, "inconsistent_metadata"),
        ({"files": {"../../escape": b"x"}}, "unsupported_wheel_layout"),
        ({"files": {"/absolute": b"x"}}, "unsupported_wheel_layout"),
        ({"files": {"back\\slash": b"x"}}, "unsupported_wheel_layout"),
        (
            {"files": {"bootstrap.pth": b"import local_probe"}},
            "unsupported_wheel_layout",
        ),
        (
            {"files": {"sitecustomize.py": b"raise RuntimeError()"}},
            "unsupported_wheel_layout",
        ),
        (
            {"files": {"local_probe-1.0.dist-info/WHEEL": b"Wheel-Version: 99\n"}},
            "unsupported_wheel_layout",
        ),
        ({"files": {"other-1.0.dist-info/METADATA": b"Name: other"}}, "invalid_wheel"),
        ({"files": {"Local_Probe.py": b"x"}}, "invalid_wheel"),
    ],
)
def test_invalid_wheels_do_not_modify_storage(
    wheel_factory, tmp_path, monkeypatch, options, code
):
    wheel, digest = wheel_factory(**options)
    monkeypatch.setattr(backend, "run_uv", lambda *a: pytest.fail("must not install"))
    root = tmp_path / "plugins"
    with pytest.raises(PluginError, match=code):
        install_extension(wheel, digest, directory=root)
    assert not root.exists()


def test_bad_hash_missing_non_wheel_and_oversized(wheel_factory, tmp_path, monkeypatch):
    wheel, digest = wheel_factory()
    for artifact, value, code in [
        (wheel, "invalid", "invalid_sha256"),
        (wheel, "0" * 64, "hash_mismatch"),
        (tmp_path / "missing.whl", digest, "invalid_wheel"),
        (tmp_path, digest, "local_wheel_required"),
        (tmp_path / "source.tar.gz", digest, "local_wheel_required"),
    ]:
        with pytest.raises(PluginError, match=code):
            install_extension(artifact, value, directory=tmp_path / "plugins")
    monkeypatch.setattr(wheel_module, "MAX_WHEEL_BYTES", 10)
    with pytest.raises(PluginError, match="wheel_too_large"):
        install_extension(wheel, digest, directory=tmp_path / "plugins")
    assert not (tmp_path / "plugins").exists()


def test_bounded_metadata_expansion_and_nonregular_input(
    wheel_factory, tmp_path, monkeypatch
):
    wheel, digest = wheel_factory()
    with monkeypatch.context() as context:
        context.setattr(wheel_module, "MAX_METADATA_BYTES", 5)
        with pytest.raises(PluginError, match="metadata_too_large"):
            wheel_module.inspect_wheel(wheel, digest)
    with monkeypatch.context() as context:
        context.setattr(wheel_module, "MAX_EXPANDED_BYTES", 5)
        with pytest.raises(PluginError, match="invalid_wheel"):
            wheel_module.inspect_wheel(wheel, digest)
    fifo = tmp_path / "fifo.whl"
    os.mkfifo(fifo)
    with pytest.raises(PluginError, match="local_wheel_required"):
        wheel_module.inspect_wheel(fifo, digest)


def test_invalid_zip_and_symlink_member(wheel_factory):
    wheel, _ = wheel_factory()
    wheel.write_bytes(b"not zip")
    with pytest.raises(PluginError, match="invalid_wheel"):
        wheel_module.inspect_wheel(
            wheel, hashlib.sha256(wheel.read_bytes()).hexdigest()
        )
    wheel, _ = wheel_factory()
    with zipfile.ZipFile(wheel, "a") as archive:
        info = zipfile.ZipInfo("link")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "somewhere")
    with pytest.raises(PluginError, match="unsupported_wheel_layout"):
        wheel_module.inspect_wheel(
            wheel, hashlib.sha256(wheel.read_bytes()).hexdigest()
        )


def test_store_rejects_core_project_and_symlinks(tmp_path, monkeypatch):
    for directory in (
        Path(sys.prefix),
        Path(sys.prefix) / "plugins",
        Path.cwd() / "plugins",
    ):
        with pytest.raises(PluginError, match="overlaps"):
            store.storage_directory(directory)
    link = tmp_path / "link"
    link.symlink_to(sys.prefix, target_is_directory=True)
    with pytest.raises(PluginError, match="invalid_plugins_directory"):
        store.storage_directory(link)
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").touch()
    monkeypatch.chdir(project)
    with pytest.raises(PluginError, match="overlaps"):
        store.storage_directory(project / "plugins")


def test_defaults_and_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert (
        store.storage_directory()
        == tmp_path / "Library/Application Support/apizr/plugins"
    )
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert store.storage_directory() == tmp_path / ".local/share/apizr/plugins"
    monkeypatch.setenv("XDG_DATA_HOME", "relative")
    with pytest.raises(PluginError, match="invalid_plugins_directory"):
        store.storage_directory()
    monkeypatch.setattr(store.os, "name", "unsupported")
    with pytest.raises(PluginError, match="unsupported_platform"):
        store.storage_directory(tmp_path)


def test_inventory_invalid_and_read_only(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    root.mkdir()
    path = root / "installations.json"
    path.write_text("not JSON")
    with pytest.raises(PluginError, match="invalid_inventory"):
        list_extensions(directory=root)
    monkeypatch.setattr(store, "MAX_INVENTORY_BYTES", 2)
    with pytest.raises(PluginError, match="invalid_inventory"):
        list_extensions(directory=root)
    path.unlink()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(PluginError, match="inventory_unavailable"):
        list_extensions(directory=root)


def test_duplicate_or_escaping_record_is_not_accepted(wheel_factory, tmp_path):
    wheel, digest = wheel_factory()
    root = tmp_path / "plugins"
    install_extension(wheel, digest, directory=root)
    path = root / "installations.json"
    original = json.loads(path.read_text())
    changed = json.loads(path.read_text())
    changed["installations"] *= 2
    path.write_text(json.dumps(changed))
    with pytest.raises(PluginError, match="invalid_inventory"):
        list_extensions(directory=root)
    original["installations"][0]["python"] = sys.executable
    path.write_text(json.dumps(original))
    with pytest.raises(PluginError, match="invalid_inventory"):
        list_extensions(directory=root)


def test_private_directory_and_lock_fail_closed(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    root.mkdir(mode=0o777)
    root.chmod(0o777)
    with pytest.raises(PluginError, match="unsafe_plugins_directory"):
        with store.installation_lock(root):
            pass
    root.chmod(0o700)
    import fcntl

    monkeypatch.setattr(fcntl, "flock", Mock(side_effect=BlockingIOError()))
    monkeypatch.setattr(store.time, "monotonic", Mock(side_effect=[0, 31]))
    with pytest.raises(PluginError, match="installation_busy"):
        with store.installation_lock(root):
            pass


def test_atomic_publish_failure_preserves_previous_inventory(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    root.mkdir()
    store.publish(root, Inventory())
    before = (root / "installations.json").read_bytes()
    with monkeypatch.context() as context:
        context.setattr(store.os, "replace", Mock(side_effect=OSError()))
        with pytest.raises(OSError):
            store.publish(root, Inventory())
    assert (root / "installations.json").read_bytes() == before
    assert not list(root.glob(".inventory-*"))
    monkeypatch.setattr(store, "MAX_INVENTORY_BYTES", 1)
    with pytest.raises(PluginError, match="inventory_full"):
        store.publish(root, Inventory())


def test_backend_timeout_and_spawn_failure(tmp_path, monkeypatch):
    import subprocess

    process = Mock()
    process.pid = 12345
    process.wait.side_effect = [subprocess.TimeoutExpired("uv", 120), 0]
    process.poll.return_value = None
    monkeypatch.setattr(backend.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(backend.os, "killpg", Mock())
    with pytest.raises(PluginError, match="uv_timeout"):
        backend.run_uv("uv", [], tmp_path)
    process.kill.assert_called_once()
    monkeypatch.setattr(backend.subprocess, "Popen", Mock(side_effect=OSError()))
    with pytest.raises(PluginError, match="uv_unavailable"):
        backend.run_uv("uv", [], tmp_path)


def test_large_description_keeps_header_and_archive_bounds(wheel_factory):
    from apizr.local_plugins.wheel import inspect_dependency, metadata_headers

    wheel, digest = wheel_factory(
        plugin=False, metadata_extra="\n" + "description " * 10000
    )
    _, distribution = inspect_dependency(wheel, digest)
    assert distribution.name == "local-probe"
    with pytest.raises(PluginError, match="metadata_too_large"):
        metadata_headers(b"X-Large: " + b"x" * 65536)
    assert "Requires-Dist" not in metadata_headers(
        b"Name: example\r\n\r\nRequires-Dist: evil"
    )

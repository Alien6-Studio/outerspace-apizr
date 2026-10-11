"""Catalog metadata, byte-bound export and existing offline installation contract."""

import json
import os
import shutil
import socket
import subprocess

import pytest

from apizr.cli import main
from apizr.plugins.catalog import (
    Catalog,
    CatalogError,
    generate_entries,
    load_catalog,
    resolve_profile,
    select_entry,
    serialize,
)
from apizr.plugins.catalog import operations as catalog_operations
from apizr.plugins.catalog.models import Identity, Profile, Provenance
from apizr.plugins.local import enable_extension, list_extensions, run_extension
from apizr.plugins.lock import check_lock
from apizr.plugins.lock import operations as lock_operations
from apizr.plugins.sync import sync_plugins
from apizr.workspace.project import load_project

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def catalog_setup(chain, tmp_path):
    plugin, digest, lock, house = chain
    shutil.copyfile(plugin, house / plugin.name)
    (house / "requirements").mkdir()
    shutil.copyfile(lock, house / "requirements/local-probe.lock")
    project = house / "apizr.toml"
    project.write_text(
        'schema_version = "apizr.project/v1"\n[[plugins]]\nname = "local-probe"\nversion = "1.0"\n'
        + f'sha256 = "{digest}"\nrequirements = "requirements/local-probe.lock"\n'
    )
    entries = generate_entries(
        project,
        house,
        descriptions={"local-probe": "Example"},
        provenance=Provenance(
            repository="https://example.org/repo", commit="a" * 40, status="development"
        ),
    )
    catalog = Catalog(
        entries=entries,
        profiles=(
            Profile(
                name="demo", plugins=(Identity(name="local-probe", version="1.0"),)
            ),
        ),
    )
    path = tmp_path / "catalogue.json"
    path.write_bytes(serialize(catalog))
    return catalog, path, house, tmp_path / "plan"


def fail(*args, **kwargs):
    pytest.fail("network/process/store side effect")


def test_static_read_only_cli_and_determinism(
    catalog_setup, monkeypatch, capsys, tmp_path
):
    catalog, path, house, output = catalog_setup
    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(subprocess, "Popen", fail)
    monkeypatch.setattr(lock_operations, "list_extensions", fail)
    monkeypatch.setenv("PATH", "")
    monkeypatch.chdir(tmp_path)
    for command in (["list"], ["show", "local-probe", "--version", "1.0"]):
        assert (
            main(["plugins", "catalog", *command, "--catalog", str(path), "--json"])
            == 0
        )
        assert json.loads(capsys.readouterr().out)
    assert (
        main(
            [
                "plugins",
                "catalog",
                "resolve",
                "--profile",
                "demo",
                "--catalog",
                str(path),
                "--wheelhouse",
                str(house),
                "--output-dir",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["installation"] == "not_performed"
    repeat = tmp_path / "repeat"
    resolve_profile(catalog, "demo", house, repeat)
    for item in output.rglob("*"):
        if item.is_file():
            assert item.read_bytes() == (repeat / item.relative_to(output)).read_bytes()
            assert str(tmp_path).encode() not in item.read_bytes()
    assert (output / "requirements/local-probe.lock").read_bytes() == (
        house / "requirements/local-probe.lock"
    ).read_bytes()
    assert check_lock(
        output / "apizr.toml", output / "apizr.plugins.lock.json", house
    ).valid
    assert load_project(output / "apizr.toml").plugins[0].name == "local-probe"
    for existing in (output, tmp_path / "empty"):
        existing.mkdir(exist_ok=True)
        with pytest.raises(CatalogError, match="output_exists"):
            resolve_profile(catalog, "demo", house, existing)
    assert not list(tmp_path.glob(".apizr-catalog-*"))


def test_export_sync_explicit_activation_and_call(catalog_setup, tmp_path):
    catalog, _, house, output = catalog_setup
    store = tmp_path / "store"
    resolve_profile(catalog, "demo", house, output)
    assert not store.exists()
    result = sync_plugins(
        output / "apizr.toml",
        output / "apizr.plugins.lock.json",
        house,
        directory=store,
    )
    assert result.exit_code == 0
    assert not list_extensions(directory=store, active=True).installations
    enable_extension("local-probe", "1.0", directory=store)
    assert run_extension("local-probe", "describe", {}, directory=store).result == 42


@pytest.mark.parametrize(
    "fault",
    [
        "schema",
        "unknown",
        "duplicate-entry",
        "duplicate-profile",
        "duplicate-selection",
        "absent-reference",
        "protocol",
        "version",
        "size",
        "path",
        "identity",
        "channel",
        "closure",
    ],
)
def test_invalid_documents(catalog_setup, fault):
    catalog, path, _, _ = catalog_setup
    document = json.loads(serialize(catalog))
    entry = document["entries"][0]
    if fault == "schema":
        document["schema_version"] = "v999"
    elif fault == "unknown":
        document["run"] = "secret"
    elif fault == "duplicate-entry":
        document["entries"].append(entry)
    elif fault == "duplicate-profile":
        document["profiles"].append(document["profiles"][0])
    elif fault == "duplicate-selection":
        document["profiles"][0]["plugins"] *= 2
    elif fault == "absent-reference":
        document["profiles"][0]["plugins"][0]["name"] = "absent"
    elif fault == "protocol":
        entry["manifest"]["protocol"] = "v999"
    elif fault == "version":
        entry["manifest"]["version"] = ">=1.0"
    elif fault == "size":
        entry["wheel"]["size"] = True
    elif fault == "path":
        entry["requirements"]["path"] = "../escape.lock"
    elif fault == "identity":
        entry["wheel"]["name"] = "other"
    elif fault == "channel":
        entry["provenance"]["status"] = "published"
    elif fault == "closure":
        entry["dependencies"] *= 2
    path.write_text(json.dumps(document))
    with pytest.raises(CatalogError, match="invalid_catalog"):
        load_catalog(path)


@pytest.mark.parametrize(
    "raw", [b"{}", b'{"entries":[],"entries":[]}', b"x" * (1024 * 1024 + 1), b"\xff"]
)
def test_malformed_and_bounded(catalog_setup, raw):
    _, path, _, _ = catalog_setup
    path.write_bytes(raw)
    with pytest.raises(CatalogError):
        load_catalog(path)


@pytest.mark.parametrize(
    "fault",
    [
        "wheel-missing",
        "wheel-altered",
        "wheel-symlink",
        "requirements-missing",
        "requirements-altered",
        "requirements-symlink",
        "parent-symlink",
        "fifo",
    ],
)
def test_artifact_refusals_no_partial_plan(catalog_setup, tmp_path, fault):
    catalog, _, house, output = catalog_setup
    entry = catalog.entries[0]
    path = house / (
        entry.wheel.filename
        if fault.startswith("wheel")
        else "requirements/local-probe.lock"
    )
    if fault.endswith("missing"):
        path.unlink()
    elif fault.endswith("altered"):
        path.write_bytes(path.read_bytes() + b"changed")
    elif fault.endswith("symlink"):
        if fault == "parent-symlink":
            path = house / "requirements"
            path.rename(house / "renamed")
            path.symlink_to(house / "renamed", target_is_directory=True)
        else:
            copy = tmp_path / "elsewhere"
            path.rename(copy)
            path.symlink_to(copy)
    elif fault == "fifo":
        path.unlink()
        os.mkfifo(path)
    with pytest.raises(CatalogError):
        resolve_profile(catalog, "demo", house, output)
    assert not output.exists() and not list(tmp_path.glob(".apizr-catalog-*"))


@pytest.mark.parametrize(
    "fault,code",
    [
        ("target", "incompatible"),
        ("apizr", "incompatible"),
        ("variant", "ambiguous"),
        ("absent", "not_in_catalog"),
    ],
)
def test_selection(catalog_setup, fault, code):
    catalog, _, house, output = catalog_setup
    document = json.loads(serialize(catalog))
    entry = document["entries"][0]
    if fault == "target":
        entry["compatibility"]["target"]["python"] = "3.99.0"
    elif fault == "apizr":
        entry["compatibility"]["apizr_version"] = "99.0"
    elif fault == "variant":
        other = json.loads(json.dumps(entry))
        other["wheel"]["sha256"] = "b" * 64
        document["entries"].append(other)
    catalog = Catalog.model_validate_json(json.dumps(document), strict=True)
    with pytest.raises(CatalogError, match=code):
        select_entry(catalog, "absent" if fault == "absent" else "local-probe", "1.0")
    with pytest.raises(CatalogError, match="unknown_profile"):
        resolve_profile(catalog, "absent", house, output)


def test_snapshots_not_reopened(catalog_setup, monkeypatch):
    catalog, _, house, output = catalog_setup
    original = catalog_operations.create_lock

    def replace_after_snapshot(project, snapshot, lock):
        for path in house.glob("*.whl"):
            path.write_bytes(b"substituted")
        return original(project, snapshot, lock)

    monkeypatch.setattr(catalog_operations, "create_lock", replace_after_snapshot)
    resolve_profile(catalog, "demo", house, output)
    assert not check_lock(
        output / "apizr.toml", output / "apizr.plugins.lock.json", house
    ).valid


def test_cancellation_removes_staging(catalog_setup, monkeypatch, tmp_path):
    catalog, _, house, output = catalog_setup

    def interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(catalog_operations, "create_lock", interrupt)
    with pytest.raises(KeyboardInterrupt):
        resolve_profile(catalog, "demo", house, output)
    assert not output.exists() and not list(tmp_path.glob(".apizr-catalog-*"))


def test_metadata_substitution_refused(catalog_setup):
    catalog, _, house, output = catalog_setup
    document = json.loads(serialize(catalog))
    document["entries"][0]["manifest"]["module"] = "other_module"
    changed = Catalog.model_validate_json(json.dumps(document), strict=True)
    with pytest.raises(CatalogError, match="artifacts_mismatch"):
        resolve_profile(changed, "demo", house, output)


def test_size_volume_and_invalid_archive(catalog_setup, monkeypatch):
    catalog, _, house, output = catalog_setup
    monkeypatch.setattr(catalog_operations.locking, "MAX_TOTAL_BYTES", 1)
    with pytest.raises(CatalogError, match="artifacts_too_large"):
        resolve_profile(catalog, "demo", house, output)


def test_cli_readable_errors(catalog_setup, capsys):
    _, path, house, output = catalog_setup
    for command in (
        ["list"],
        ["show", "local-probe", "--version", "1.0"],
        [
            "resolve",
            "--profile",
            "demo",
            "--wheelhouse",
            str(house),
            "--output-dir",
            str(output),
        ],
    ):
        assert main(["plugins", "catalog", *command, "--catalog", str(path)]) == 0
        assert capsys.readouterr().out
    assert main(["plugins", "catalog", "list", "--catalog", "absent"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "invalid_catalog" in captured.err


def test_same_identity_wheel_variants_in_house_refused(catalog_setup):
    catalog, _, house, output = catalog_setup
    primary = house / catalog.entries[0].wheel.filename
    shutil.copyfile(primary, house / primary.name.replace("-py3-", "-1-py3-"))
    with pytest.raises(CatalogError, match="ambiguous_wheel"):
        resolve_profile(catalog, "demo", house, output)
    assert not output.exists()


def test_schema_stays_in_sync():
    from pathlib import Path

    expected = json.loads(
        Path("docs/specs/apizr-plugin-catalog-v1.schema.json").read_text()
    )
    assert Catalog.model_json_schema() == expected


def test_dependency_free_entry_and_no_import(wheel_factory, tmp_path):
    marker = tmp_path / "executed"
    wheel, digest = wheel_factory(
        files={
            "local_probe.py": f"from pathlib import Path\nPath({str(marker)!r}).touch()\n".encode()
        }
    )
    house = tmp_path / "house"
    house.mkdir()
    shutil.copyfile(wheel, house / wheel.name)
    project = tmp_path / "apizr.toml"
    project.write_text(
        'schema_version = "apizr.project/v1"\n[[plugins]]\nname = "local-probe"\nversion = "1.0"\n'
        + f'sha256 = "{digest}"\n'
    )
    entries = generate_entries(
        project,
        house,
        descriptions={"local-probe": "No imports"},
        provenance=Provenance(
            repository="https://example.org/repo", commit="a" * 40, status="development"
        ),
    )
    catalog = Catalog(
        entries=entries,
        profiles=(
            Profile(
                name="demo", plugins=(Identity(name="local-probe", version="1.0"),)
            ),
        ),
    )
    resolve_profile(catalog, "demo", house, tmp_path / "plan")
    assert not marker.exists()


@pytest.mark.parametrize("fault", ["requirements", "wheel", "missing", "invalid"])
def test_generation_checks_reopened_bytes(catalog_setup, monkeypatch, tmp_path, fault):
    from apizr.plugins.catalog import generation

    _, _, house, _ = catalog_setup
    original = generation.create_lock

    def substitute(*args):
        result = original(*args)
        if fault == "requirements":
            (house / "requirements/local-probe.lock").write_bytes(b"altered")
        elif fault == "wheel":
            next(house.glob("local_probe*.whl")).write_bytes(b"altered")
        elif fault == "missing":
            next(house.glob("local_probe*.whl")).unlink()
        return result

    if fault == "invalid":
        next(house.glob("local_probe*.whl")).write_bytes(b"invalid")
    monkeypatch.setattr(generation, "create_lock", substitute)
    with pytest.raises(CatalogError):
        generate_entries(
            house / "apizr.toml",
            house,
            descriptions={"local-probe": "Test"},
            provenance=Provenance(
                repository="https://example.org/repo",
                commit="a" * 40,
                status="development",
            ),
        )

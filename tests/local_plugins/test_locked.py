"""Real offline installations from bounded, hash-locked wheel snapshots."""

import hashlib
import json
import os
import sys

import pytest

from apizr.cli import main
from apizr.local_plugins import (
    PluginError,
    backend,
    enable_extension,
    install_extension,
    install_from_source,
    list_extensions,
    locking,
    run_extension,
)

pytestmark = pytest.mark.timeout(25)


def install(chain, root):
    plugin, digest, lock, wheelhouse = chain
    return install_extension(
        plugin, digest, requirements=lock, wheelhouse=wheelhouse, directory=root
    )


def test_transitive_cli_install_activation_and_inventory(
    chain, tmp_path, capsys, monkeypatch
):
    plugin, digest, lock, wheelhouse = chain
    root = tmp_path / "plugins"
    # No inherited index, config, proxy, target or Python path can affect uv.
    monkeypatch.setenv("UV_INDEX_URL", "http://127.0.0.1:1/must-not-connect")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    before_env, before_path = dict(os.environ), list(sys.path)
    assert (
        main(
            [
                "plugins",
                "install",
                str(plugin),
                "--sha256",
                digest,
                "--requirements",
                str(lock),
                "--wheelhouse",
                str(wheelhouse),
                "--plugins-dir",
                str(root),
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "Installed local-probe 1.0\n"
    record = list_extensions(directory=root).installations[0]
    assert record.lock_sha256 == hashlib.sha256(lock.read_bytes()).hexdigest()
    assert [item.name for item in record.dependencies] == [
        "locked-helper",
        "locked-leaf",
    ]
    assert all(
        item.version == "1.0" and len(item.sha256) == 64 for item in record.dependencies
    )
    assert not list_extensions(directory=root, active=True).installations
    with pytest.raises(PluginError, match="plugin_inactive"):
        run_extension("local-probe", "describe", {}, directory=root)
    enable_extension("local-probe", "1.0", directory=root)
    assert run_extension("local-probe", "describe", {}, directory=root).result == 42
    assert main(["plugins", "list", "--json", "--plugins-dir", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["installations"][0]["dependencies"] == [
        item.model_dump() for item in record.dependencies
    ]
    assert before_env == dict(os.environ) and before_path == sys.path
    assert not {"locked_helper", "locked_leaf", "local_probe"} & set(sys.modules)


@pytest.mark.parametrize(
    "change,error",
    [
        ("missing_file", "missing_locked_wheel"),
        ("missing_pin", "uv_install_failed"),
        ("incompatible", "uv_install_failed"),
        ("wrong_hash", "hash_mismatch"),
        ("wrong_plugin", "plugin_lock_mismatch"),
        ("wrong_version", "dependency_lock_mismatch"),
    ],
)
def test_incomplete_or_invalid_graph_refused(
    chain, tmp_path, change, error, wheel_factory
):
    _, digest, lock, wheelhouse = chain
    leaf = next(wheelhouse.glob("locked_leaf*"))
    content = lock.read_text()
    if change == "missing_file":
        leaf.unlink()
    elif change == "missing_pin":
        leaf.unlink()
        lock.write_text(
            "\n".join(
                line
                for line in content.splitlines()
                if not line.startswith("locked-leaf")
            )
        )
    elif change == "incompatible":
        # Valid wheel and lock, but helper still requires leaf==1.0.
        leaf.unlink()
        built, _ = wheel_factory(
            name="locked-leaf",
            version="2.0",
            plugin=False,
            files={"locked_leaf.py": b"VALUE = 42\n"},
        )
        leaf = built.rename(wheelhouse / built.name)
        lines = [
            line for line in content.splitlines() if not line.startswith("locked-leaf")
        ]
        lock.write_text(
            "\n".join(lines)
            + f"\nlocked-leaf==2.0 --hash=sha256:{hashlib.sha256(leaf.read_bytes()).hexdigest()}\n"
        )
    elif change == "wrong_hash":
        leaf.write_bytes(leaf.read_bytes() + b"tampered")
    elif change == "wrong_plugin":
        lock.write_text(content.replace(digest, "0" * 64))
    else:
        lock.write_text(content.replace("locked-leaf==1.0", "locked-leaf==2.0"))
    root = tmp_path / "plugins"
    with pytest.raises(PluginError, match=error):
        install(chain, root)
    assert list_extensions(directory=root).installations == []
    assert not list((root / "environments").iterdir())


@pytest.mark.parametrize(
    "line",
    [
        "-r other.lock",
        "-c constraints.txt",
        "--index-url https://example.org",
        "--extra-index-url https://example.org",
        "--find-links ./elsewhere",
        "--trusted-host example.org",
        "-e .",
        "name @ https://example.org/x.whl",
        "./x.whl",
        "name>=1.0",
        "name==1.*",
        "name[extra]==1.0",
        'name==1.0; python_version>="3.11"',
        "name==1.0 --no-deps",
        "name==1.0 --hash=md5:abc",
        "",
        "name===1.0",
    ],
)
def test_lock_subset_rejects_unsupported_input(tmp_path, line):
    path = tmp_path / "requirements.lock"
    path.write_text(line)
    with pytest.raises(PluginError, match="invalid_requirements_lock"):
        locking.read_lock(path)


def test_comments_continuations_and_duplicate_names(tmp_path):
    path = tmp_path / "requirements.lock"
    path.write_text(
        "# uv-style lock\nSome_Package==1.0 \\\n    --hash=sha256:"
        + "A" * 64
        + " # reviewed\n"
    )
    lock = locking.read_lock(path)
    assert (
        lock.packages[0].name == "some-package" and lock.packages[0].sha256 == "a" * 64
    )
    path.write_text(path.read_text() + "some.package==1.0 --hash=sha256:" + "a" * 64)
    with pytest.raises(PluginError, match="duplicate_locked_distribution"):
        locking.read_lock(path)


def test_reinstall_identity_conflict_and_legacy_reading(
    chain, tmp_path, monkeypatch, wheel_factory
):
    root = tmp_path / "plugins"
    old_wheel, old_hash = wheel_factory(name="old-plugin")
    old = install_extension(old_wheel, old_hash, directory=root)
    path = root / "installations.json"
    legacy = json.loads(path.read_text())
    legacy["installations"][0].pop("dependencies")
    legacy["installations"][0].pop("lock_sha256")
    path.write_text(json.dumps(legacy))
    assert list_extensions(directory=root).installations == [old]
    record = install(chain, root)
    enable_extension("local-probe", "1.0", directory=root)
    before = path.read_bytes(), (root / "activations.json").read_bytes()
    monkeypatch.setattr(
        backend,
        "run_uv",
        lambda *a: pytest.fail("Idempotent installation must not invoke uv"),
    )
    assert install(chain, root) == record
    chain[2].write_text(chain[2].read_text() + "# new lock identity\n")
    with pytest.raises(PluginError, match="installation_conflict"):
        install(chain, root)
    assert before == (path.read_bytes(), (root / "activations.json").read_bytes())


@pytest.mark.parametrize("tamper_private", [False, True])
def test_snapshots_and_uv_hash_verification(
    chain, tmp_path, monkeypatch, tamper_private
):
    run = backend.run_uv

    def change(executable, arguments, work):
        if arguments[0] == "pip":
            paths = (
                (work / "wheels").glob("*.whl")
                if tamper_private
                else chain[3].glob("*.whl")
            )
            for path in paths:
                path.write_bytes(path.read_bytes() + b"changed after validation")
            chain[2].write_text("untrusted replacement")
        run(executable, arguments, work)

    monkeypatch.setattr(backend, "run_uv", change)
    root = tmp_path / "plugins"
    if tamper_private:
        with pytest.raises(PluginError, match="uv_install_failed"):
            install(chain, root)
        assert not list_extensions(directory=root).installations
    else:
        record = install(chain, root)
        enable_extension(record.name, record.version, directory=root)
        assert run_extension(record.name, "describe", {}, directory=root).result == 42


@pytest.mark.parametrize("option", ["requirements", "wheelhouse"])
def test_options_must_be_paired_before_network(tmp_path, monkeypatch, option):
    monkeypatch.setattr(backend, "require_uv", lambda: pytest.fail("No backend"))
    with pytest.raises(PluginError, match="requirements_and_wheelhouse_required"):
        install_from_source(
            "https://invalid.invalid/a.whl", "a" * 64, **{option: tmp_path}
        )


def test_limits_and_special_files(chain, tmp_path, monkeypatch):
    lock = chain[2]
    monkeypatch.setattr(locking, "MAX_LOCK_BYTES", 1)
    with pytest.raises(PluginError, match="requirements_lock_too_large"):
        locking.read_lock(lock)
    monkeypatch.setattr(locking, "MAX_LOCK_BYTES", 65536)
    monkeypatch.setattr(locking, "MAX_WHEELS", 1)
    with pytest.raises(PluginError, match="too_many_locked_wheels"):
        locking.read_lock(lock)
    monkeypatch.setattr(locking, "MAX_WHEELS", 128)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(PluginError, match="invalid_requirements_lock"):
        locking.read_lock(fifo)
    monkeypatch.setattr(locking, "MAX_TOTAL_BYTES", 1)
    with pytest.raises(PluginError, match="wheelhouse_too_large"):
        install(chain, tmp_path / "plugins")


@pytest.mark.parametrize(
    "filename",
    [
        "bad.pth",
        "BAD.PTH",
        "sitecustomize.py",
        "sitecustomize.pyc",
        "usercustomize.cpython-314-darwin.so",
        "sitecustomize/__init__.py",
        "dep.data/purelib/usercustomize.py",
        "../escape",
        "/absolute",
    ],
)
def test_dependency_archive_startup_protections(
    chain, tmp_path, wheel_factory, filename
):
    plugin, digest, lock, wheelhouse = chain
    dep, dep_hash = wheel_factory(
        name="locked-leaf",
        plugin=False,
        files={filename: b"raise RuntimeError('must not execute')"},
    )
    dep.replace(wheelhouse / dep.name)
    lines = [
        line
        for line in lock.read_text().splitlines()
        if not line.startswith("locked-leaf")
    ]
    lock.write_text("\n".join(lines) + f"\nlocked-leaf==1.0 --hash=sha256:{dep_hash}\n")
    with pytest.raises(PluginError, match="unsupported_wheel_layout"):
        install(chain, tmp_path / "plugins")


@pytest.mark.parametrize("failure", [KeyboardInterrupt, OSError])
def test_interruption_preserves_activations(
    chain, tmp_path, wheel_factory, monkeypatch, failure
):
    root = tmp_path / "plugins"
    old_wheel, old_hash = wheel_factory(name="old-plugin")
    old = install_extension(old_wheel, old_hash, directory=root)
    enable_extension(old.name, old.version, directory=root)
    before = (root / "activations.json").read_bytes()
    run = backend.run_uv

    def interrupt(executable, arguments, work):
        run(executable, arguments, work)
        if arguments[0] == "pip":
            raise failure()

    with monkeypatch.context() as context:
        context.setattr(backend, "run_uv", interrupt)
        with pytest.raises((PluginError, KeyboardInterrupt)):
            install(chain, root)
    assert list_extensions(directory=root).installations == [old]
    assert (root / "activations.json").read_bytes() == before
    assert len(list((root / "environments").iterdir())) == 1
    assert install(chain, root).dependencies


@pytest.mark.parametrize(
    "case,error",
    [
        ("unlocked", "unlocked_wheel"),
        ("duplicate", "ambiguous_locked_wheel"),
        ("symlink", "local_wheel_required"),
        ("fifo", "local_wheel_required"),
        ("count", "too_many_locked_wheels"),
        ("expanded", "wheelhouse_too_large"),
    ],
)
def test_wheelhouse_boundaries(chain, tmp_path, monkeypatch, case, error):
    wheelhouse = chain[3]
    leaf = next(wheelhouse.glob("locked_leaf*"))
    if case == "unlocked":
        (wheelhouse / "unknown-1.0-py3-none-any.whl").write_bytes(b"unused")
    elif case == "duplicate":
        (wheelhouse / "locked_leaf-1.0-1-py3-none-any.whl").write_bytes(
            leaf.read_bytes()
        )
    elif case == "symlink":
        moved = leaf.rename(tmp_path / leaf.name)
        leaf.symlink_to(moved)
    elif case == "fifo":
        leaf.unlink()
        os.mkfifo(leaf)
    elif case == "count":
        for i in range(129):
            (wheelhouse / str(i)).touch()
    else:
        monkeypatch.setattr(locking, "MAX_TOTAL_EXPANDED_BYTES", 1)
    with pytest.raises(PluginError, match=error):
        install(chain, tmp_path / "plugins")


@pytest.mark.parametrize("case", ["python", "platform", "direct-reference"])
def test_uv_compatibility_and_direct_references(chain, tmp_path, wheel_factory, case):
    _, digest, lock, wheelhouse = chain
    old = next(wheelhouse.glob("locked_leaf*"))
    old.unlink()
    kwargs = {}
    if case == "platform":
        kwargs["filename"] = "locked_leaf-1.0-cp39-cp39-win32.whl"
    else:
        kwargs["metadata_extra"] = (
            "Requires-Python: >=99\n"
            if case == "python"
            else "Requires-Dist: unpinned @ https://invalid.invalid/secret.whl\n"
        )
    wheel, digest = wheel_factory(
        name="locked-leaf",
        plugin=False,
        files={"locked_leaf.py": b"VALUE = 41\n"},
        **kwargs,
    )
    wheel.rename(wheelhouse / wheel.name)
    lines = [
        line
        for line in lock.read_text().splitlines()
        if not line.startswith("locked-leaf")
    ]
    lock.write_text("\n".join(lines) + f"\nlocked-leaf==1.0 --hash=sha256:{digest}\n")
    with pytest.raises(
        PluginError,
        match="unsupported_dependency_reference"
        if case == "direct-reference"
        else "uv_install_failed",
    ):
        install(chain, tmp_path / "plugins")


def test_locked_https_uses_one_request_and_offline_uv(chain, tmp_path, monkeypatch):
    from http.server import BaseHTTPRequestHandler

    from test_download import certificate, https_server

    from apizr.local_plugins import install_from_url

    plugin, digest, lock, wheelhouse = chain
    cert_dir = tmp_path / "cert"
    cert_dir.mkdir()
    cert, key = certificate(cert_dir)
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(plugin.read_bytes())

    popen = backend.subprocess.Popen
    invocations = []

    def observe(argv, **kwargs):
        if "--offline" in argv:
            invocations.append(argv)
            assert "--no-config" in argv and "--no-cache" in argv
            assert set(kwargs["env"]) == {"HOME", "TMPDIR", "UV_PYTHON_DOWNLOADS"}
            if "install" in argv:
                for required in (
                    "--no-index",
                    "--no-build",
                    "--no-sources",
                    "--require-hashes",
                    "--strict",
                ):
                    assert required in argv
                assert "--no-deps" not in argv
        return popen(argv, **kwargs)

    monkeypatch.setattr(backend.subprocess, "Popen", observe)
    with https_server(cert, key, Handler) as url:
        monkeypatch.setenv("UV_INDEX_URL", url + "/index")
        monkeypatch.setenv("HTTPS_PROXY", url)
        record = install_from_url(
            url + "/" + plugin.name,
            digest,
            requirements=lock,
            wheelhouse=wheelhouse,
            directory=tmp_path / "plugins",
            ca_file=cert,
        )
    assert len(calls) == 1 and len(invocations) == 2
    assert len(record.dependencies) == 2


def test_dependencies_never_imported_during_install(chain, tmp_path, wheel_factory):
    marker = tmp_path / "must-not-execute"
    dep, digest = wheel_factory(
        name="locked-leaf",
        plugin=False,
        files={
            "locked_leaf.py": f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('must not run')\n".encode()
        },
    )
    dep.replace(chain[3] / dep.name)
    lines = [
        line
        for line in chain[2].read_text().splitlines()
        if not line.startswith("locked-leaf")
    ]
    chain[2].write_text(
        "\n".join(lines) + f"\nlocked-leaf==1.0 --hash=sha256:{digest}\n"
    )
    assert install(chain, tmp_path / "plugins").dependencies
    assert not marker.exists()


def test_locked_concurrent_installs_publish_one_environment(chain, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    root = tmp_path / "plugins"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: install(chain, root), range(2)))
    assert results[0] == results[1]
    assert list_extensions(directory=root).installations == [results[0]]
    assert len(list((root / "environments").iterdir())) == 1


def test_installed_metadata_verified_before_publication(chain, tmp_path, monkeypatch):
    run = backend.run_uv

    def corrupt(executable, arguments, work):
        run(executable, arguments, work)
        if arguments[0] == "pip":
            path = next(
                (work.parent / "venv/lib").glob(
                    "python*/site-packages/locked_leaf-*.dist-info/METADATA"
                )
            )
            path.write_text(path.read_text().replace("Version: 1.0", "Version: 9.0"))

    monkeypatch.setattr(backend, "run_uv", corrupt)
    root = tmp_path / "plugins"
    with pytest.raises(PluginError, match="installed_dependencies_mismatch"):
        install(chain, root)
    assert not list_extensions(directory=root).installations


def test_missing_lock_and_no_dependency_options(chain, tmp_path):
    with pytest.raises(PluginError, match="dependencies_not_supported"):
        install_extension(chain[0], chain[1], directory=tmp_path / "plugins")
    chain[2].unlink()
    with pytest.raises(PluginError, match="invalid_requirements_lock"):
        install(chain, tmp_path / "plugins")
    assert not (tmp_path / "plugins").exists()


def test_sigint_during_locked_install_preserves_existing(
    chain, tmp_path, wheel_factory
):
    import shutil
    import signal
    import subprocess
    import time

    root = tmp_path / "plugins"
    old_wheel, old_hash = wheel_factory(name="old-plugin")
    old = install_extension(old_wheel, old_hash, directory=root)
    enable_extension(old.name, old.version, directory=root)
    before = (
        (root / "installations.json").read_bytes(),
        (root / "activations.json").read_bytes(),
    )
    real_uv = shutil.which("uv")
    assert real_uv
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "installer-pid"
    wrapper = bin_dir / "uv"
    wrapper.write_text(
        f"#!{sys.executable}\nimport os,sys,subprocess,time\nfrom pathlib import Path\n"
        f"subprocess.run([{real_uv!r}, *sys.argv[1:]], check=True, timeout=10)\n"
        f"if 'install' in sys.argv:\n    Path({str(marker)!r}).write_text(str(os.getpid()))\n    time.sleep(30)\n"
    )
    wrapper.chmod(0o700)
    plugin, digest, lock, wheelhouse = chain
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-m",
            "apizr.cli",
            "plugins",
            "install",
            str(plugin),
            "--sha256",
            digest,
            "--requirements",
            str(lock),
            "--wheelhouse",
            str(wheelhouse),
            "--plugins-dir",
            str(root),
        ],
        env={**os.environ, "PATH": str(bin_dir)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        process.send_signal(signal.SIGINT)
        out, err = process.communicate(timeout=5)
        assert process.returncode == 130 and not out
        assert err == b"apizr plugins: installation_interrupted\n"
        with pytest.raises(ProcessLookupError):
            os.kill(int(marker.read_text()), 0)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)
        if marker.exists():
            try:
                os.killpg(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
    assert before == (
        (root / "installations.json").read_bytes(),
        (root / "activations.json").read_bytes(),
    )
    assert len(list((root / "environments").iterdir())) == 1
    assert install(chain, root).dependencies

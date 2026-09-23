"""Real verified HTTPS transfers and offline installs, with bounded failure paths."""

import hashlib
import importlib.util
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from apizr.cli import main
from apizr.local_plugins import (
    DownloadCancelled,
    DownloadLimits,
    PluginError,
    disable_extension,
    download,
    enable_extension,
    install_extension,
    install_from_source,
    install_from_url,
    list_extensions,
    run_extension,
)
from apizr.local_plugins import wheel as wheel_module

SPEC = importlib.util.spec_from_file_location(
    "https_fixture", Path(__file__).resolve().parents[2] / "scripts/https_fixture.py"
)
assert SPEC is not None and SPEC.loader is not None
fixture_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture_module)
certificate, https_server = fixture_module.certificate, fixture_module.https_server

pytestmark = pytest.mark.timeout(25)


@pytest.fixture(scope="module")
def tls(tmp_path_factory):
    return certificate(tmp_path_factory.mktemp("https-cert"))


@pytest.fixture
def endpoint(tls, wheel_factory, request):
    wheel, digest = wheel_factory(**getattr(request, "param", {}))
    requests = []
    started = threading.Event()
    stopped = threading.Event()
    body = wheel.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append((self.path, dict(self.headers)))
            path = urlsplit(self.path).path
            try:
                if path.startswith("/redirect/"):
                    count = int(path.split("/")[2])
                    self.send_response(302)
                    self.send_header(
                        "Location",
                        f"/redirect/{count - 1}/{wheel.name}"
                        if count
                        else f"/{wheel.name}",
                    )
                    self.send_header("Set-Cookie", "credential=secret")
                    self.end_headers()
                    return
                redirects = {
                    "/loop/": f"/loop/{wheel.name}",
                    "/http/": "http://localhost/never.whl",
                    "/credentials/": "https://user:secret@localhost/never.whl",
                    "/bad-location/": "https://localhost:bad/never.whl",
                    "/no-location/": None,
                }
                for prefix, location in redirects.items():
                    if path.startswith(prefix):
                        self.send_response(302)
                        if location:
                            self.send_header("Location", location)
                        self.end_headers()
                        return
                if path.startswith("/error/"):
                    self.send_error(403)
                    return
                if path.startswith("/headers/"):
                    started.set()
                    stopped.wait(3)
                self.send_response(200)
                if path.startswith("/declared-big/"):
                    self.send_header("Content-Length", str(64 * 1024 * 1024 + 1))
                elif path.startswith("/broken/"):
                    self.send_header("Content-Length", str(len(body) + 10))
                elif path.startswith("/invalid-length/"):
                    self.send_header("Content-Length", "-1")
                elif path.startswith("/encoding/"):
                    self.send_header("Content-Encoding", "gzip")
                elif path.startswith("/chunked/"):
                    self.send_header("Transfer-Encoding", "chunked")
                elif not path.startswith(("/stream/", "/slow/", "/invalid/")):
                    self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Content-Disposition", 'attachment; filename="../../outside.whl"'
                )
                self.end_headers()
                if path.startswith("/slow/"):
                    started.set()
                    while not stopped.wait(0.02):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                elif path.startswith("/chunked/"):
                    self.wfile.write(
                        f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n"
                    )
                elif path.startswith("/stream/"):
                    self.wfile.write(b"x" * 4096)
                elif path.startswith("/invalid/"):
                    self.wfile.write(b"not-a-wheel")
                else:
                    self.wfile.write(body)
            except (OSError, ValueError):
                pass

    with https_server(*tls, Handler) as url:
        yield url, wheel, digest, requests, started, stopped
        stopped.set()


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    root = tmp_path / "downloads"
    root.mkdir()
    monkeypatch.setattr(download.tempfile, "tempdir", str(root))
    yield root
    assert list(root.iterdir()) == []


def test_https_install_lifecycle_idempotence_and_headers(
    endpoint, tls, scratch, tmp_path, monkeypatch, capsys, wheel_factory
):
    url, wheel, digest, requests, _, _ = endpoint
    root = tmp_path / "plugins"
    monkeypatch.setenv("SSL_CERT_FILE", str(tls[0]))
    monkeypatch.setenv("HTTPS_PROXY", "http://secret:secret@invalid:1")
    monkeypatch.setenv("HTTP_COOKIE", "credential=secret")
    monkeypatch.setenv("AUTHORIZATION", "Bearer secret")
    monkeypatch.setenv("NETRC", str(tmp_path / "netrc"))
    (tmp_path / "netrc").write_text("machine localhost login secret password secret\n")
    source = f"{url}/redirect/4/{wheel.name}?token=secret"
    assert (
        main(
            [
                "plugins",
                "install",
                source,
                "--sha256",
                digest,
                "--plugins-dir",
                str(root),
                "--python",
                sys.executable,
            ]
        )
        == 0
    )
    assert "Installed local-probe 1.0" in capsys.readouterr().out
    record = list_extensions(directory=root).installations[0]
    assert not list_extensions(directory=root, active=True).installations
    with pytest.raises(PluginError, match="plugin_inactive"):
        run_extension(record.name, "describe", {}, directory=root)
    enable_extension(record.name, record.version, directory=root)
    before = (root / "activations.json").read_bytes()
    assert (
        install_from_url(f"{url}/{wheel.name}", digest, directory=root, ca_file=tls[0])
        == record
    )
    assert (root / "activations.json").read_bytes() == before
    assert run_extension(record.name, "describe", {}, directory=root).status == "ok"
    disable_extension(record.name, directory=root)
    # A lower-level library client sends neither ambient credentials nor redirect cookies.
    assert len(requests) == 7
    assert all(
        not (
            {k.lower() for k in headers}
            & {"authorization", "proxy-authorization", "cookie"}
        )
        for _, headers in requests
    )
    assert not (tmp_path / "outside.whl").exists()


@pytest.mark.parametrize(
    "prefix,code",
    [
        ("loop", "too_many_redirects"),
        ("redirect/5", "too_many_redirects"),
        ("http", "invalid_plugin_url"),
        ("credentials", "invalid_plugin_url"),
        ("bad-location", "invalid_plugin_url"),
        ("no-location", "invalid_plugin_url"),
        ("error", "download_failed"),
        ("declared-big", "wheel_too_large"),
        ("broken", "download_incomplete"),
        ("invalid-length", "download_failed"),
        ("encoding", "download_failed"),
    ],
)
def test_failed_transfers_preserve_existing_states(
    endpoint, tls, scratch, tmp_path, prefix, code
):
    url, wheel, digest, _, _, _ = endpoint
    root = tmp_path / "plugins"
    record = install_extension(wheel, digest, directory=root)
    enable_extension(record.name, record.version, directory=root)
    before = {path.name: path.read_bytes() for path in root.glob("*.json")}
    with pytest.raises(PluginError) as error:
        install_from_url(
            f"{url}/{prefix}/{wheel.name}?secret=SECRET",
            digest,
            directory=root,
            ca_file=tls[0],
        )
    assert str(error.value) == code
    assert before == {path.name: path.read_bytes() for path in root.glob("*.json")}
    assert run_extension(record.name, "describe", {}, directory=root).status == "ok"


def test_invalid_wheel_hash_certificate_and_hostname(endpoint, tls, scratch, tmp_path):
    url, wheel, digest, _, _, _ = endpoint
    root = tmp_path / "plugins"
    cases = [
        (f"{url}/{wheel.name}", "0" * 64, tls[0], "hash_mismatch"),
        (
            f"{url}/invalid/{wheel.name}",
            hashlib.sha256(b"not-a-wheel").hexdigest(),
            tls[0],
            "invalid_wheel",
        ),
        (f"{url}/{wheel.name}", digest, None, "download_tls_failed"),
        (
            f"{url.replace('localhost', '127.0.0.1')}/{wheel.name}",
            digest,
            tls[0],
            "download_tls_failed",
        ),
    ]
    for source, expected, ca, code in cases:
        with pytest.raises(PluginError, match=f"^{code}$"):
            install_from_url(source, expected, directory=root, ca_file=ca)
        assert not root.exists()
        assert list(scratch.iterdir()) == []


def test_size_without_content_length_and_chunked(
    endpoint, tls, scratch, tmp_path, monkeypatch
):
    url, wheel, digest, _, _, _ = endpoint
    with monkeypatch.context() as context:
        context.setattr(wheel_module, "MAX_WHEEL_BYTES", 2048)
        with pytest.raises(PluginError, match="wheel_too_large"):
            install_from_url(
                f"{url}/stream/{wheel.name}",
                digest,
                directory=tmp_path / "plugins",
                ca_file=tls[0],
            )
    assert (
        install_from_url(
            f"{url}/chunked/{wheel.name}",
            digest,
            directory=tmp_path / "plugins",
            ca_file=tls[0],
        ).sha256
        == digest
    )


@pytest.mark.parametrize(
    "source",
    [
        "http://host/a.whl",
        "ftp://host/a.whl",
        "file:///a.whl",
        "https:/a.whl",
        "//host/a.whl",
        "https://user:secret@host/a.whl",
        "https://host:bad/a.whl",
        "https://host/%2fescape.whl",
        "https://host/%5cescape.whl",
        "https://host/%00.whl",
        "https://host/a.whl#fragment",
        " https://host/a.whl",
        "https://host/a.whl\n",
        "https://host/download",
        "https://host:0/a.whl",
        "https://host/\\a.whl",
    ],
)
def test_invalid_urls_never_become_local_paths_or_make_requests(source, monkeypatch):
    monkeypatch.setattr(
        download, "install_extension", lambda *a, **k: pytest.fail("local fallback")
    )
    monkeypatch.setattr(
        download.backend, "require_uv", lambda: pytest.fail("before URL validation")
    )
    with pytest.raises(PluginError, match="invalid_plugin_url"):
        install_from_source(source, "a" * 64)


def test_hash_limits_backend_and_precancel_checked_before_download(
    endpoint, tls, scratch, monkeypatch
):
    url, wheel, digest, requests, _, _ = endpoint
    source = f"{url}/{wheel.name}"
    with pytest.raises(PluginError, match="invalid_sha256"):
        install_from_url(source, "invalid", ca_file=tls[0])
    with pytest.raises(PluginError, match="invalid_download_limits"):
        install_from_url(
            source, digest, limits=DownloadLimits.model_construct(total_timeout_ms=-1)
        )
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DownloadCancelled):
        install_from_url(source, digest, cancel=cancel)
    monkeypatch.setenv("PATH", "")
    with pytest.raises(PluginError, match="uv_not_found"):
        install_from_url(source, digest)
    assert requests == []
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize(
    "prefix,limits",
    [
        ("headers", DownloadLimits(read_timeout_ms=100)),
        ("slow", DownloadLimits(read_timeout_ms=100, total_timeout_ms=400)),
    ],
)
def test_read_and_total_deadlines(endpoint, tls, scratch, tmp_path, prefix, limits):
    url, wheel, digest, _, _, _ = endpoint
    start = time.monotonic()
    with pytest.raises(PluginError, match="download_timeout"):
        install_from_url(
            f"{url}/{prefix}/{wheel.name}",
            digest,
            directory=tmp_path / "plugins",
            ca_file=tls[0],
            limits=limits,
        )
    assert time.monotonic() - start < 3
    assert not (tmp_path / "plugins").exists()


def test_cancellation_closes_process_and_cleans_partial_file(
    endpoint, tls, scratch, tmp_path, monkeypatch
):
    url, wheel, digest, _, started, _ = endpoint
    cancel = threading.Event()
    processes = []
    original = subprocess.Popen

    def track(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(download.subprocess, "Popen", track)
    with ThreadPoolExecutor() as pool:
        call = pool.submit(
            install_from_url,
            f"{url}/slow/{wheel.name}",
            digest,
            directory=tmp_path / "plugins",
            ca_file=tls[0],
            cancel=cancel,
        )
        try:
            assert started.wait(3)
            deadline = time.monotonic() + 2
            while (
                not list(scratch.glob("*/" + wheel.name))
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert list(scratch.glob("*/" + wheel.name))
        finally:
            cancel.set()
        with pytest.raises(DownloadCancelled):
            call.result(timeout=3)
    assert list(scratch.iterdir()) == []
    assert processes and all(process.poll() is not None for process in processes)
    assert not (tmp_path / "plugins").exists()
    assert install_from_url(
        f"{url}/{wheel.name}", digest, directory=tmp_path / "plugins", ca_file=tls[0]
    )


def test_cli_interrupt_cleans_partial_download_and_redacts(endpoint, tls, tmp_path):
    url, wheel, digest, _, started, _ = endpoint
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-m",
            "apizr.cli",
            "plugins",
            "install",
            f"{url}/slow/{wheel.name}?token=SECRET",
            "--sha256",
            digest,
            "--plugins-dir",
            str(tmp_path / "plugins"),
        ],
        env={**os.environ, "SSL_CERT_FILE": str(tls[0]), "TMPDIR": str(temporary)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert started.wait(3)
        process.send_signal(signal.SIGINT)
        out, err = process.communicate(timeout=3)
        assert process.returncode == 130 and out == b""
        assert err == b"apizr plugins: installation_interrupted\n"
        assert list(temporary.iterdir()) == []
        assert not (tmp_path / "plugins").exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=3)


def test_local_source_stays_offline_and_other_operations_do_not_download(
    wheel_factory, tmp_path, monkeypatch
):
    wheel, digest = wheel_factory()
    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: pytest.fail("network")
    )
    monkeypatch.setattr(download, "_download", lambda *a, **k: pytest.fail("download"))
    root = tmp_path / "plugins"
    record = install_from_source(str(wheel), digest, directory=root)
    assert list_extensions(directory=root).installations == [record]
    enable_extension(record.name, record.version, directory=root)
    assert run_extension(record.name, "describe", {}, directory=root).status == "ok"
    disable_extension(record.name, directory=root)


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("redirect/4", 0),
        ("chunked", 0),
        ("loop", 8),
        ("http", 2),
        ("no-location", 2),
        ("error", 3),
        ("broken", 9),
        ("invalid-length", 3),
        ("encoding", 3),
        ("stream", 6),
        ("declared-big", 6),
        ("invalid", 7),
        ("headers", 5),
    ],
)
def test_worker_transfer_contract(
    endpoint, tls, tmp_path, monkeypatch, prefix, expected
):
    """Exercise the actual stdlib worker contract separately from its supervisor."""
    import json

    from apizr.local_plugins import _download_worker

    url, wheel, digest, _, _, _ = endpoint
    destination = tmp_path / "transfer.whl"
    control = tmp_path / "control.json"
    control.write_text(
        json.dumps(
            {
                "url": f"{url}/{prefix}/{wheel.name}",
                "destination": str(destination),
                "sha256": digest,
                "max_bytes": 2048 if prefix == "stream" else 64 * 1024 * 1024,
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 100 if prefix == "headers" else 1000,
                "ca_file": str(tls[0]),
            }
        )
    )
    monkeypatch.setattr(sys, "argv", ["worker", str(control)])
    assert _download_worker.main() == expected
    if expected == 0:
        assert destination.read_bytes() == wheel.read_bytes()
        # Exclusive creation refuses any existing target without overwriting it.
        assert _download_worker.main() == 3
        assert destination.read_bytes() == wheel.read_bytes()


def test_worker_rejects_untrusted_tls(endpoint, tmp_path, monkeypatch):
    import json

    from apizr.local_plugins import _download_worker

    url, wheel, digest, _, _, _ = endpoint
    control = tmp_path / "control.json"
    control.write_text(
        json.dumps(
            {
                "url": f"{url}/{wheel.name}",
                "destination": str(tmp_path / "transfer.whl"),
                "sha256": digest,
                "max_bytes": 2048,
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 1000,
                "ca_file": None,
            }
        )
    )
    monkeypatch.setattr(sys, "argv", ["worker", str(control)])
    assert _download_worker.main() == 4
    assert not (tmp_path / "transfer.whl").exists()


def test_remote_version_selection_and_content_conflict(
    endpoint, tls, scratch, tmp_path, wheel_factory
):
    url, wheel, digest, _, _, _ = endpoint
    source = f"{url}/{wheel.name}"
    root = tmp_path / "plugins"
    newer, newer_hash = wheel_factory(version="2.0")
    selected = install_extension(newer, newer_hash, directory=root)
    enable_extension(selected.name, selected.version, directory=root)
    before = (root / "activations.json").read_bytes()
    incoming = install_from_url(source, digest, directory=root, ca_file=tls[0])
    assert incoming.version == "1.0"
    assert (root / "activations.json").read_bytes() == before
    assert list_extensions(directory=root, active=True).installations == [selected]
    conflict_root = tmp_path / "conflict"
    changed, changed_hash = wheel_factory(files={"extra.txt": b"different contents"})
    existing = install_extension(changed, changed_hash, directory=conflict_root)
    enable_extension(existing.name, existing.version, directory=conflict_root)
    before = {p.name: p.read_bytes() for p in conflict_root.glob("*.json")}
    with pytest.raises(PluginError, match="installation_conflict"):
        install_from_url(source, digest, directory=conflict_root, ca_file=tls[0])
    assert before == {p.name: p.read_bytes() for p in conflict_root.glob("*.json")}


@pytest.mark.parametrize(
    "endpoint,code",
    [
        ({"metadata_extra": "Requires-Dist: requests\n"}, "dependencies_not_supported"),
        (
            {"manifest_changes": {"protocol": "apizr.extension/v999"}},
            "invalid_manifest",
        ),
        ({"manifest_changes": {"version": "3.0"}}, "inconsistent_metadata"),
    ],
    indirect=["endpoint"],
)
def test_https_reuses_local_wheel_validation(endpoint, tls, scratch, tmp_path, code):
    url, wheel, digest, _, _, _ = endpoint
    with pytest.raises(PluginError, match=f"^{code}$"):
        install_from_url(
            f"{url}/{wheel.name}",
            digest,
            directory=tmp_path / "plugins",
            ca_file=tls[0],
        )
    assert not (tmp_path / "plugins").exists()


def test_tls_handshake_has_connect_deadline(tls, scratch, tmp_path):
    stopped = threading.Event()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(3)

        def accept():
            connection, _ = listener.accept()
            with connection:
                stopped.wait(3)

        thread = threading.Thread(target=accept)
        thread.start()
        try:
            start = time.monotonic()
            with pytest.raises(PluginError, match="download_timeout"):
                install_from_url(
                    f"https://localhost:{listener.getsockname()[1]}/probe-1-py3-none-any.whl",
                    "a" * 64,
                    directory=tmp_path / "plugins",
                    ca_file=tls[0],
                    limits=DownloadLimits(connect_timeout_ms=100),
                )
            assert time.monotonic() - start < 2
        finally:
            stopped.set()
            thread.join(timeout=4)
        assert not thread.is_alive()


def test_total_deadline_bounds_blocked_name_resolution(
    endpoint, tls, scratch, tmp_path, monkeypatch
):
    from apizr.local_plugins import _download_worker

    url, wheel, digest, requests, _, _ = endpoint
    wrapper = tmp_path / "blocked_dns.py"
    wrapper.write_text(
        "import socket,time,runpy\n"
        "def blocked(*args, **kwargs): time.sleep(10)\n"
        "socket.getaddrinfo=blocked\n"
        f"runpy.run_path({_download_worker.__file__!r}, run_name='__main__')\n"
    )
    monkeypatch.setattr(_download_worker, "__file__", str(wrapper))
    start = time.monotonic()
    with pytest.raises(PluginError, match="download_timeout"):
        install_from_url(
            f"{url}/{wheel.name}",
            digest,
            directory=tmp_path / "plugins",
            ca_file=tls[0],
            limits=DownloadLimits(total_timeout_ms=300),
        )
    assert time.monotonic() - start < 2
    assert requests == []

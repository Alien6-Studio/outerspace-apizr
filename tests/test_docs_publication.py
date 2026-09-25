"""Publication requires exact content, not a stale/newer 200 or build success."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load("check_docs_site")
build = load("docs_build")
https = load("https_fixture")


@pytest.fixture(scope="module")
def tls(tmp_path_factory):
    return https.certificate(tmp_path_factory.mktemp("docs-cert"))


@pytest.fixture
def site(tmp_path):
    for name, token in build.CRITICAL.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"<html>{token}</html>")
    for name in build.ASSETS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    config = SimpleNamespace(site_dir=tmp_path, extra={})
    build.on_config(config)
    # This test builds fixture content, not a deployable checkout.
    config.extra["docs_build"]["source_dirty"] = False
    build.on_post_build(config)
    return tmp_path


def handler(site, mutate=lambda name, data: data):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            name = self.path.lstrip("/")
            data = mutate(name, (site / name).read_bytes())
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def test_exact_https_content_and_explicit_trust(site, tls):
    with https.https_server(*tls, handler(site)) as url:
        checker.probe(site, url, str(tls[0]))
        with pytest.raises(OSError):
            checker.probe(site, url)  # no insecure certificate fallback


@pytest.mark.parametrize("change", ["older", "newer", "content", "status"])
def test_stale_newer_or_mixed_deployment_is_not_success(site, tls, change):
    def mutate(name, data):
        if name == "build-info.json" and change != "content":
            marker = json.loads(data)
            if change == "status":
                marker["status"] = "stable"
            else:
                marker["source_commit"] = ("a" if change == "older" else "b") * 40
            return json.dumps(marker).encode()
        if name == "index.html" and change == "content":
            return b"<html>A generic HTTP 200 page</html>"
        return data

    with https.https_server(*tls, handler(site, mutate)) as url:
        with pytest.raises(ValueError, match="mismatch"):
            checker.probe(site, url, str(tls[0]))


def test_deployment_switch_during_probe(site, tls):
    reads = 0

    def mutate(name, data):
        nonlocal reads
        if name == "build-info.json":
            reads += 1
            if reads > 1:
                marker = json.loads(data)
                marker["source_commit"] = "b" * 40
                return json.dumps(marker).encode()
        return data

    with https.https_server(*tls, handler(site, mutate)) as url:
        with pytest.raises(ValueError, match="changed during"):
            checker.probe(site, url, str(tls[0]))


def test_total_deadline_kills_slow_probe(site, tls):
    released = __import__("threading").Event()

    class Slow(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            released.wait(5)

    try:
        with https.https_server(*tls, Slow) as url:
            started = time.monotonic()
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "check_docs_site.py"),
                    "--site",
                    str(site),
                    "--url",
                    url,
                    "--ca-file",
                    str(tls[0]),
                    "--timeout",
                    "1",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert result.returncode == 1
            assert "not confirmed within 1s" in result.stderr
            assert time.monotonic() - started < 4
    finally:
        released.set()


@pytest.mark.parametrize(
    "status,commit",
    [("building", "a" * 40), ("built", "b" * 40), ("errored", "a" * 40)],
)
def test_pages_must_publish_expected_generated_commit(monkeypatch, status, commit):
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            stdout=json.dumps({"status": status, "commit": commit})
        ),
    )
    with pytest.raises(ValueError, match="GitHub Pages"):
        checker.pages_ready("owner/repo", "a" * 40, 1)


def test_marker_uses_source_commit_and_fingerprints(site):
    marker = checker.marker_at(site)
    assert (
        marker["source_commit"]
        == subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=SCRIPTS, text=True
        ).strip()
    )
    assert marker["status"] == "development"
    assert marker["stable_release"] == "0.3.0"
    assert (
        marker["files"]["index.html"]
        == hashlib.sha256((site / "index.html").read_bytes()).hexdigest()
    )


def test_critical_content_required(site):
    (site / "index.html").write_text("wrong home page")
    with pytest.raises(ValueError, match="Missing documentation content"):
        build.on_post_build(SimpleNamespace(site_dir=site, extra={"docs_build": {}}))


def test_dirty_checkout_cannot_be_confirmed(site):
    path = site / "build-info.json"
    marker = json.loads(path.read_bytes())
    marker["source_dirty"] = True
    path.write_text(json.dumps(marker))
    with pytest.raises(ValueError, match="dirty checkout"):
        checker.wait_for_site(SimpleNamespace(site=site))


def test_wait_confirms_exact_content(site, tls, capsys):
    with https.https_server(*tls, handler(site)) as url:
        checker.wait_for_site(
            SimpleNamespace(
                site=site,
                url=url,
                ca_file=str(tls[0]),
                timeout=5,
                repository=None,
                deployment_commit=None,
            )
        )
    assert "Verified public source" in capsys.readouterr().out


@pytest.mark.parametrize("status", [301, 404, 500])
def test_http_status_and_redirect_are_refused(tls, status):
    class Refusal(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(status)
            self.send_header("Location", "http://localhost/insecure")
            self.end_headers()

    with https.https_server(*tls, Refusal) as url:
        with pytest.raises(ValueError, match=f"HTTPS status {status}"):
            checker.read_https(url, "index.html", str(tls[0]))


def test_public_body_is_bounded(site, tls, monkeypatch):
    monkeypatch.setattr(checker, "MAX_BYTES", 128)
    with https.https_server(*tls, handler(site, lambda name, data: b"x" * 256)) as url:
        with pytest.raises(ValueError, match="exceeds 128"):
            checker.read_https(url, "index.html", str(tls[0]))


def test_invalid_public_marker_is_refused(site, tls):
    with https.https_server(*tls, handler(site, lambda name, data: b"not JSON")) as url:
        with pytest.raises(ValueError):
            checker.probe(site, url, str(tls[0]))


def test_http_url_refused_before_network():
    with pytest.raises(ValueError, match="HTTPS"):
        checker.read_https("http://localhost", "index.html")


def test_pages_ready_requires_separate_public_probe(monkeypatch):
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            stdout=json.dumps({"status": "built", "commit": "a" * 40})
        ),
    )
    checker.pages_ready("owner/repo", "a" * 40, 1)

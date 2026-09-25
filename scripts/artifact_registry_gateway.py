"""Disposable read-only HTTPS gateway to the real Zot fixture.

Faults alter real responses, never manufacture a successful proof. No request
headers, credentials or native diagnostics are logged.
"""

import http.client
import json
import ssl
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path("/proof/artifact-consumer")
CONTEXT = ssl.create_default_context(cafile="/proof/certs/ca.crt")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def send(self, status, body=b"", headers=None):
        self.send_response(status)
        for name, value in (headers or {}).items():
            if name.lower() not in {
                "connection",
                "transfer-encoding",
                "content-length",
            }:
                self.send_header(name, value)
        self.send_header(
            "Content-Length",
            (headers or {}).get("Content-Length", "0")
            if self.command == "HEAD"
            else str(len(body)),
        )
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        mode = (
            (ROOT / "gateway-mode").read_text()
            if (ROOT / "gateway-mode").exists()
            else ""
        )
        if mode == "missing-api" and "/referrers/" in self.path:
            self.send(404, b"API disabled by test")
            return
        upstream = http.client.HTTPSConnection(
            "registry-backend.test", 5443, context=CONTEXT, timeout=20
        )
        try:
            upstream.request(
                self.command,
                self.path,
                headers={
                    "Host": "registry.test:5443",
                    "Authorization": self.headers.get("Authorization", ""),
                    "Accept": self.headers.get("Accept", "*/*"),
                },
            )
            response = upstream.getresponse()
            body = response.read(16 * 1024 * 1024 + 1)
            assert len(body) <= 16 * 1024 * 1024
            headers = dict(response.getheaders())
            if response.status == 200 and self.command == "GET":
                if mode == "pagination" and "/referrers/" in self.path:
                    value = json.loads(body)
                    assert len(value["manifests"]) == 3
                    if "fixture_page" not in parse_qs(urlsplit(self.path).query):
                        value["manifests"] = value["manifests"][:1]
                        headers["Link"] = (
                            "<" + self.path + '&fixture_page=2>; rel="next"'
                        )
                    else:
                        value["manifests"] = value["manifests"][1:]
                        (ROOT / "pagination-observed").touch()
                    body = json.dumps(value).encode()
                if (mode == "blob-corrupt" and "/blobs/" in self.path) or (
                    mode == "manifest-corrupt" and "/manifests/" in self.path
                ):
                    body = body[:-1] + bytes([body[-1] ^ 1])
                if mode == "slow-blob" and "/blobs/" in self.path:
                    (ROOT / "blocked-transfer").touch()
                    deadline = time.monotonic() + 30
                    while not (ROOT / "release-transfer").exists():
                        if time.monotonic() >= deadline:
                            break
                        time.sleep(0.02)
            self.send(response.status, body, headers)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            upstream.close()

    do_HEAD = do_GET

    def refused(self):
        self.send(403, b"read-only consumer")

    do_POST = do_PUT = do_PATCH = do_DELETE = refused


def main():
    server = ThreadingHTTPServer(("0.0.0.0", 5443), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain("/proof/certs/ca.crt", "/proof/certs/key.pem")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

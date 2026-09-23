"""Disposable localhost HTTPS fixture with an explicitly trusted test certificate."""

import ssl
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer


class LocalHTTPServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        # HTTPServer normally reverse-resolves the bind address. A loopback
        # fixture already knows its name and must not depend on runner DNS.
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


def certificate(directory: Path) -> tuple[Path, Path]:
    cert, key = directory / "localhost.pem", directory / "localhost-key.pem"
    config = directory / "openssl.cnf"
    config.write_text(
        "[req]\nprompt=no\ndistinguished_name=subject\nx509_extensions=extensions\n"
        "[subject]\nCN=localhost\n[extensions]\nsubjectAltName=DNS:localhost\n"
        "basicConstraints=critical,CA:TRUE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign,cRLSign\n"
        "extendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid:always\n"
    )
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "2",
            "-config",
            str(config),
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    key.chmod(0o600)
    return cert, key


@contextmanager
def https_server(cert: Path, key: Path, handler: type[BaseHTTPRequestHandler]):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    server = LocalHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    # Bound even malformed clients/handshakes in this test-only server.
    server.socket.settimeout(2)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}
    )
    thread.start()
    try:
        yield f"https://localhost:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()

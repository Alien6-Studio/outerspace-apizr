"""Disposable RFC 3161 fixture. No machine trust, public TSA or production key."""

import contextlib
import http.server
import subprocess
import threading
from pathlib import Path


def command(*args, cwd=None):
    result = subprocess.run(
        list(map(str, args)), cwd=cwd, capture_output=True, timeout=30
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout


@contextlib.contextmanager
def authority(root: Path, *, received=None, release=None):
    root.mkdir(mode=0o700)
    command(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        root / "ca.key",
        "-out",
        root / "ca.crt",
        "-days",
        "1",
        "-subj",
        "/CN=Apizr disposable TSA CA",
        "-addext",
        "basicConstraints=critical,CA:TRUE",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
    )
    command(
        "openssl",
        "req",
        "-new",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        root / "tsa.key",
        "-out",
        root / "tsa.csr",
        "-subj",
        "/CN=Apizr disposable timestamp signer",
    )
    (root / "extensions").write_text(
        "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=critical,timeStamping\n"
    )
    command(
        "openssl",
        "x509",
        "-req",
        "-in",
        root / "tsa.csr",
        "-CA",
        root / "ca.crt",
        "-CAkey",
        root / "ca.key",
        "-CAcreateserial",
        "-out",
        root / "tsa.crt",
        "-days",
        "1",
        "-extfile",
        root / "extensions",
    )
    (root / "serial").write_text("01\n")
    (root / "tsa.cnf").write_text(f"""[tsa]
default_tsa = local
[local]
serial = {root}/serial
signer_cert = {root}/tsa.crt
certs = {root}/ca.crt
signer_key = {root}/tsa.key
signer_digest = sha256
default_policy = 1.2.3.4.1
other_policies = 1.2.3.4.2
digests = sha256
accuracy = secs:1
ordering = yes
tsa_name = yes
ess_cert_id_chain = yes
ess_cert_id_alg = sha256
""")
    calls = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            self.connection.settimeout(5)
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                self.send_error(400)
                return
            (root / "request.der").write_bytes(self.rfile.read(size))
            if received is not None:
                received.set()
            if release is not None and not release.wait(20):
                self.send_error(503)
                return
            reply = command(
                "openssl",
                "ts",
                "-reply",
                "-config",
                root / "tsa.cnf",
                "-queryfile",
                root / "request.der",
            )
            calls.append(True)
            self.send_response(200)
            self.send_header("Content-Type", "application/timestamp-reply")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            try:
                self.wfile.write(reply)
            except BrokenPipeError:
                pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", root / "ca.crt", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)

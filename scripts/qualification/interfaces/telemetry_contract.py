"""Export the public schema or run its disposable loopback-only CI receiver.

This conformance stub has no persistence, production destination or forwarding.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from apizr.telemetry.model import MAX_REPORT_BYTES, UsageReport, decode_report


class Handler(BaseHTTPRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(2)

    def log_message(self, format: str, *args: object) -> None:
        # Do not retain URLs, addresses, headers or accepted/rejected bodies.
        pass

    def _reply(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()
        self.close_connection = True

    def do_POST(self) -> None:
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if (
                self.path != "/"
                or self.headers.get("Content-Type") != "application/json"
                or len(lengths) != 1
                or self.headers.get("Transfer-Encoding") is not None
                or not lengths[0].isascii()
                or not lengths[0].isdecimal()
            ):
                raise ValueError()
            length = int(lengths[0])
            if not 0 < length <= MAX_REPORT_BYTES:
                self._reply(413)
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError()
            decode_report(raw)
        except (OSError, ValueError):
            self._reply(400)
            return
        self._reply(204)


def make_server() -> HTTPServer:
    return HTTPServer(("127.0.0.1", 0), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-schema", action="store_true")
    args = parser.parse_args()
    if args.export_schema:
        path = (
            Path(__file__).resolve().parents[3]
            / "docs/specs/apizr-telemetry-v1.schema.json"
        )
        path.write_text(
            json.dumps(UsageReport.model_json_schema(), indent=2) + "\n",
            encoding="utf-8",
        )
        return
    with make_server() as server:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()

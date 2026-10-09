"""Private stdlib-only HTTPS worker; its parent owns the overall deadline."""

import hashlib
import http.client
import json
import re
import ssl
import sys
from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import SplitResult, unquote, urljoin, urlsplit

ERRORS = {
    2: "invalid_plugin_url",
    3: "download_failed",
    4: "download_tls_failed",
    5: "download_timeout",
    6: "wheel_too_large",
    7: "hash_mismatch",
    8: "too_many_redirects",
    9: "download_incomplete",
}


class DownloadFailure(Exception):
    def __init__(self, code: int) -> None:
        self.code = code
        super().__init__(ERRORS[code])


class Transfer(TypedDict):
    url: str
    destination: str
    sha256: str
    max_bytes: int
    connect_timeout_ms: int
    read_timeout_ms: int
    ca_file: str | None


def validate_url(url: str) -> SplitResult:
    try:
        if (
            len(url) > 16384
            or any(ord(c) <= 32 or ord(c) >= 127 for c in url)
            or "\\" in url
        ):
            raise ValueError()
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.port == 0
        ):
            raise ValueError()
        return parsed
    except ValueError:
        raise DownloadFailure(2) from None


def wheel_filename(url: str) -> str:
    parsed = validate_url(url)
    name = unquote(parsed.path.rsplit("/", 1)[-1])
    if len(name) > 255 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.!+-]*\.whl", name):
        raise DownloadFailure(2)
    return name


def transfer(request: Transfer) -> None:
    # Default trust (or an explicitly supplied CA) always checks certificate and host.
    context = ssl.create_default_context(cafile=request["ca_file"])
    context.set_alpn_protocols(["http/1.1"])
    url = request["url"]
    for redirects in range(6):
        parsed = validate_url(url)
        assert parsed.hostname is not None
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            parsed.port,
            timeout=request["connect_timeout_ms"] / 1000,
            context=context,
        )
        try:
            connection.connect()
            assert connection.sock is not None
            connection.sock.settimeout(request["read_timeout_ms"] / 1000)
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            # No proxy, cookie jar, netrc, Authorization or inherited headers.
            connection.request("GET", target, headers={"Accept-Encoding": "identity"})
            with connection.getresponse() as response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader("Location")
                    if not location:
                        raise DownloadFailure(2)
                    # Validate raw locations before urljoin can discard controls.
                    if (
                        any(ord(c) <= 32 or ord(c) >= 127 for c in location)
                        or "\\" in location
                    ):
                        raise DownloadFailure(2)
                    url = urljoin(url, location)
                    validate_url(url)
                    if redirects == 5:
                        raise DownloadFailure(8)
                    continue
                if response.status != 200:
                    raise DownloadFailure(3)
                length = response.getheader("Content-Length")
                expected = None if length is None else int(length)
                if expected is not None and expected < 0:
                    raise DownloadFailure(3)
                if expected is not None and expected > request["max_bytes"]:
                    raise DownloadFailure(6)
                if response.getheader("Content-Encoding", "identity") != "identity":
                    raise DownloadFailure(3)
                # Ignore Content-Disposition. Exclusive creation uses the vetted initial name.
                digest = hashlib.sha256()
                size = 0
                with Path(request["destination"]).open("xb") as target_file:
                    while True:
                        block = response.read(
                            min(65536, request["max_bytes"] - size + 1)
                        )
                        if not block:
                            break
                        size += len(block)
                        if size > request["max_bytes"]:
                            raise DownloadFailure(6)
                        digest.update(block)
                        target_file.write(block)
                if expected is not None and size != expected:
                    raise DownloadFailure(9)
                if digest.hexdigest() != request["sha256"].lower():
                    raise DownloadFailure(7)
                return
        finally:
            connection.close()


def main() -> int:
    try:
        # Only the parent writes this private control file, never the server.
        request = cast(Transfer, json.loads(Path(sys.argv[1]).read_text()))
        transfer(request)
        return 0
    except DownloadFailure as error:
        return error.code
    except ssl.SSLError:
        return 4
    except TimeoutError:
        return 5
    except http.client.IncompleteRead:
        return 9
    except (OSError, ValueError, http.client.HTTPException):
        return 3


if __name__ == "__main__":
    sys.exit(main())

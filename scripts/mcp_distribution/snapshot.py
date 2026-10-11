"""Verify MCPfinder's documented, digest-bound SQLite snapshot without running it."""

import gzip
import hashlib
import io
import json
import re
import sqlite3
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

from .http import fetch, fetch_json
from .metadata import REPOSITORY_URL
from .providers import mcpfinder, outcome

BASE = "https://mcpfinder.dev/api/v1/snapshot"
MAX_COMPRESSED = 128 * 1024 * 1024
MAX_RAW = 512 * 1024 * 1024


def inspect_snapshot(
    manifest: dict, compressed: bytes, version: str, *, now=None
) -> dict:
    identity = manifest["sha256"]
    if (
        not re.fullmatch(r"[0-9a-f]{64}", identity)
        or len(compressed) > MAX_COMPRESSED
        or len(compressed) != manifest["sizeBytes"]
        or hashlib.sha256(compressed).hexdigest() != identity
    ):
        return outcome("mismatch", "MCPfinder snapshot digest/size mismatch")
    published = datetime.fromisoformat(manifest["publishedAt"].replace("Z", "+00:00"))
    age = ((now or datetime.now(timezone.utc)) - published).total_seconds()
    if age < -300 or age > 18 * 3600:
        return outcome(
            "stale", "MCPfinder snapshot is outside its documented freshness window"
        )
    with tempfile.TemporaryDirectory(prefix="apizr-mcpfinder-") as directory:
        path = Path(directory) / "snapshot.sqlite"
        size = 0
        with (
            gzip.GzipFile(fileobj=io.BytesIO(compressed)) as source,
            path.open("wb") as target,
        ):
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_RAW:
                    return outcome(
                        "temporarily_unavailable",
                        "Expanded snapshot exceeds the configured bound",
                    )
                target.write(chunk)
        if size != manifest.get("rawSizeBytes"):
            return outcome("mismatch", "Expanded snapshot size differs from manifest")
        connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA query_only=ON")
            # Bounded fixed SELECT; no source-provided SQL, extension or trigger runs.
            steps = 0

            def bound():
                nonlocal steps
                steps += 1
                return int(steps > 10000)

            connection.set_progress_handler(bound, 1000)
            connection.row_factory = sqlite3.Row
            rows = [
                dict(row)
                for row in connection.execute(
                    "SELECT repository_url, version, package_identifier, transport_type, status, sources "
                    "FROM servers WHERE repository_url = ? LIMIT 3",
                    (REPOSITORY_URL,),
                )
            ]
        finally:
            connection.close()
    for row in rows:
        row["sources"] = json.loads(row["sources"])
    return {
        **mcpfinder(rows, version),
        "snapshot_sha256": identity,
        "published_at": manifest["publishedAt"],
    }


def live_snapshot(version: str) -> dict:
    manifest, error = fetch_json(BASE + "/manifest.json")
    if error:
        return error
    assert manifest is not None
    identity = manifest.get("sha256", "")
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
        return outcome("temporarily_unavailable", "Invalid MCPfinder manifest")
    size = manifest.get("sizeBytes")
    raw_size = manifest.get("rawSizeBytes")
    if (
        type(size) is not int
        or type(raw_size) is not int
        or not 0 < size <= MAX_COMPRESSED
        or not 0 < raw_size <= MAX_RAW
    ):
        return outcome("temporarily_unavailable", "Snapshot exceeds the download bound")
    # Never follow a URL supplied by the snapshot to another host.
    compressed, error = fetch(
        BASE + "/data.sqlite.gz?sha=" + identity, limit=MAX_COMPRESSED
    )
    if error:
        return error
    assert compressed is not None
    try:
        return inspect_snapshot(manifest, compressed, version)
    except (
        KeyError,
        TypeError,
        ValueError,
        OSError,
        EOFError,
        zlib.error,
        sqlite3.Error,
    ):
        return outcome(
            "temporarily_unavailable", "Snapshot format could not be verified"
        )

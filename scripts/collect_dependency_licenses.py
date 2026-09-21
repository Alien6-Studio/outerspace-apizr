"""Collect hashed upstream notices for review, without executing package code.

The output is a new candidate file, never an approved inventory. Review component
licenses and scopes before editing policy/dependency-licenses.json.
"""

import argparse
import hashlib
import io
import json
import re
import tarfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

from check_dependency_sources import validate_sources

MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_NOTICE_BYTES = 2 * 1024 * 1024
NOTICE = re.compile(
    r"(^|/)(licen[sc]e(?:[-.][a-z0-9_.-]+)?|copying(?:[-.][a-z0-9_.-]+)?|"
    r"notice(?:[-.][a-z0-9_.-]+)?|copyright|third.party.notices(?:\.md)?|"
    r"[^/]+\.LICENSE|[^/]+\.ABOUT)$",
    re.IGNORECASE,
)


def notices(data: bytes, archive: dict) -> list[dict]:
    if "sha256:" + hashlib.sha256(data).hexdigest() != archive["hash"]:
        raise ValueError("Archive SHA-256 does not match uv.lock")
    result = []

    def add(path: str, raw: bytes) -> None:
        if len(raw) > MAX_NOTICE_BYTES:
            raise ValueError(f"Oversized notice: {path}")
        result.append(
            {
                "path": path,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "text": raw.decode("utf-8"),
            }
        )

    # Read individual members in memory. Never extract paths, run setup.py,
    # import package modules, or follow archive symlinks.
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as archive_file:
            for member in archive_file.infolist():
                if not member.is_dir() and NOTICE.search(member.filename):
                    if member.file_size > MAX_NOTICE_BYTES:
                        raise ValueError(f"Oversized notice: {member.filename}")
                    add(member.filename, archive_file.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as archive_file:
            for member in archive_file:
                if member.isfile() and NOTICE.search(member.name):
                    if member.size > MAX_NOTICE_BYTES:
                        raise ValueError(f"Oversized notice: {member.name}")
                    stream = archive_file.extractfile(member)
                    if stream is None:
                        raise ValueError(f"Unreadable notice: {member.name}")
                    with stream:
                        add(member.name, stream.read(MAX_NOTICE_BYTES + 1))
    if not result or len({f["path"] for f in result}) != len(result):
        raise ValueError(
            "Missing or duplicate notice paths; inspect the archive manually"
        )
    return sorted(result, key=lambda f: f["path"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package", action="append", help="Locked name; repeat to select several"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New candidate JSON file"
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite an existing review or candidate")
    root = Path(__file__).resolve().parents[1]
    lock = tomllib.loads((root / "uv.lock").read_text())
    validate_sources(lock, "outerspace-apizr")
    packages = [p for p in lock["package"] if "registry" in p["source"]]
    if args.package:
        if set(args.package) - {p["name"] for p in packages}:
            parser.error("Requested package is absent from the universal lock")
        packages = [p for p in packages if p["name"] in args.package]
    candidates = []
    for package in packages:
        archive = package.get("sdist") or min(
            package["wheels"], key=lambda a: a["size"]
        )
        with urllib.request.urlopen(archive["url"], timeout=60) as response:
            data = response.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ValueError(f"Oversized archive: {package['name']}")
        candidates.append(
            {
                "name": package["name"],
                "version": package["version"],
                "status": "pending",
                "archive": archive,
                "license_files": notices(data, archive),
            }
        )
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(
            {"schema_version": 1, "packages": candidates},
            stream,
            indent=2,
            ensure_ascii=False,
        )
        stream.write("\n")
    print(f"Collected {len(candidates)} candidates; no license approval was granted")


if __name__ == "__main__":
    main()

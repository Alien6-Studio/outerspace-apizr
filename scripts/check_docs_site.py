"""Verify exact generated content, then wait boundedly for Pages and public HTTPS.

The probe is a killable child: DNS, TLS and a slow body cannot exceed the parent's
remaining total deadline. There is no HTTP/insecure fallback or redirect following.
"""

import argparse
import hashlib
import http.client
import json
import re
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 8 * 1024 * 1024


def marker_at(site: Path) -> dict:
    marker = json.loads((site / "build-info.json").read_bytes())
    if (
        marker.get("schema") != "apizr.docs-build/v1"
        or not re.fullmatch(r"[0-9a-f]{40}", marker.get("source_commit", ""))
        or marker.get("status") != "development"
        or not isinstance(marker.get("source_dirty"), bool)
        or not isinstance(marker.get("files"), dict)
    ):
        raise ValueError("Invalid documentation build marker")
    for name, digest in marker["files"].items():
        path = Path(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or hashlib.sha256((site / path).read_bytes()).hexdigest() != digest
        ):
            raise ValueError(f"Invalid local build fingerprint: {name}")
    return marker


def read_https(base: str, name: str, ca_file: str | None = None) -> bytes:
    url = urlsplit(base)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("An explicit HTTPS site URL without credentials is required")
    context = ssl.create_default_context(cafile=ca_file)
    connection = http.client.HTTPSConnection(
        url.hostname, url.port, timeout=10, context=context
    )
    try:
        connection.request(
            "GET",
            url.path.rstrip("/") + "/" + name,
            headers={"Cache-Control": "no-cache", "Accept-Encoding": "identity"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"{name}: HTTPS status {response.status} (no redirects)")
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError(f"{name}: response exceeds {MAX_BYTES} bytes")
        return data
    finally:
        connection.close()


def probe(site: Path, base: str, ca_file: str | None = None) -> None:
    expected = marker_at(site)
    observed = json.loads(read_https(base, "build-info.json", ca_file))
    if observed != expected:
        raise ValueError(
            "Public marker mismatch: expected source "
            f"{expected['source_commit']}, observed {observed.get('source_commit')}; "
            "a newer deployment is not confirmation of this one"
        )
    for name, digest in expected["files"].items():
        data = read_https(base, name, ca_file)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Public content mismatch: {name}")
    # Catch a deployment switching during the page/asset reads as well.
    if json.loads(read_https(base, "build-info.json", ca_file)) != expected:
        raise ValueError("Public marker changed during verification")


def pages_ready(repository: str, deployment_commit: str, timeout: float) -> None:
    result = subprocess.run(
        ["gh", "api", f"repos/{repository}/pages/builds/latest"],
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )
    build = json.loads(result.stdout)
    if build.get("commit") != deployment_commit or build.get("status") != "built":
        raise ValueError(
            f"GitHub Pages: expected {deployment_commit} built; "
            f"observed {build.get('commit')} {build.get('status')}"
        )


def wait_for_site(args) -> None:
    marker = marker_at(args.site)
    if marker["source_dirty"]:
        raise ValueError("Refusing to confirm a deployment built from a dirty checkout")
    if bool(args.repository) != bool(args.deployment_commit):
        raise ValueError("repository and deployment-commit must be provided together")
    deadline = time.monotonic() + args.timeout
    attempt = 0
    last_error = "No attempt completed"
    while time.monotonic() < deadline:
        attempt += 1
        try:
            if args.repository:
                pages_ready(
                    args.repository,
                    args.deployment_commit,
                    min(20, max(0.01, deadline - time.monotonic())),
                )
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--probe",
                "--site",
                str(args.site),
                "--url",
                args.url,
            ]
            if args.ca_file:
                command += ["--ca-file", args.ca_file]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=min(45, max(0.01, deadline - time.monotonic())),
            )
            if result.returncode:
                raise ValueError(result.stderr.strip())
            print(
                f"Verified public source {marker['source_commit']} "
                f"(development), deployment {args.deployment_commit or 'not queried'}"
            )
            return
        except (ValueError, subprocess.SubprocessError) as error:
            last_error = str(error)
            print(f"Attempt {attempt}: {last_error}", flush=True)
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    raise ValueError(f"Publication not confirmed within {args.timeout}s: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument("--url", default="https://apizr.outerspace.sh/")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--repository")
    parser.add_argument("--deployment-commit")
    parser.add_argument("--ca-file", help="Explicit CA for a disposable HTTPS fixture")
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 900:
        parser.error("timeout must be between 1 and 900 seconds")
    try:
        if args.probe:
            probe(args.site, args.url, args.ca_file)
        else:
            wait_for_site(args)
    except (ValueError, OSError, http.client.HTTPException) as error:
        print(f"Documentation verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

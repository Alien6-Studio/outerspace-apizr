"""Inspect distribution evidence without publishing; network access requires --live."""

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from build_mcp_bundle import build
from mcp_distribution import providers
from mcp_distribution.http import fetch, fetch_json
from mcp_distribution.metadata import ROOT, candidate_artifacts, read, validate_metadata
from mcp_distribution.snapshot import live_snapshot


def checked(url, check, *, token=None):
    payload, error = fetch_json(url, token=token)
    if error:
        return error
    try:
        return check(payload)
    except (KeyError, TypeError, ValueError, AttributeError):
        return providers.outcome(
            "temporarily_unavailable", "Provider response shape is not supported"
        )


def inspect_smithery(name, token, discovery, expected_bundle):
    if not name:
        return providers.outcome(
            "not_checked",
            "Supply the stable qualified name chosen during the authorized Smithery submission",
        )
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
        return providers.outcome("mismatch", "Invalid Smithery qualified name")
    base = "https://api.smithery.ai/servers/" + quote(name, safe="")
    payload, error = fetch_json(base, token=token)
    if error:
        return error
    assert payload is not None
    if payload.get("qualifiedName") != name:
        return providers.outcome(
            "mismatch", "Smithery returned a different qualified name"
        )
    try:
        # Download uses the provider-owned stable route, never a response-supplied URL.
        bundle = None
        if expected_bundle:
            with tempfile.TemporaryDirectory(
                prefix="apizr-mcpb-identity-"
            ) as directory:
                reconstructed = Path(directory) / "server.mcpb"
                build(reconstructed)
                if expected_bundle.read_bytes() != reconstructed.read_bytes():
                    return providers.outcome(
                        "mismatch",
                        "Expected MCPB does not match the released wrapper sources",
                    )
            bundle, error = fetch(
                base + "/download", token=token, limit=4 * 1024 * 1024
            )
            if error:
                return error
            if bundle != expected_bundle.read_bytes():
                return providers.outcome(
                    "mismatch",
                    "Smithery bundle differs from the qualified reproducible MCPB",
                )
        return providers.smithery(
            payload,
            discovery,
            read(ROOT / "plugins/mcp/distribution/manifest.json"),
            bundle,
        )
    except (KeyError, TypeError, ValueError, OSError):
        return providers.outcome(
            "temporarily_unavailable",
            "Smithery installation evidence could not be verified",
        )


def verify(args) -> dict:
    descriptor = validate_metadata()
    version = descriptor["version"]
    expected = candidate_artifacts(read(args.candidate), version, args.source_sha)
    discovery = read(args.discovery)
    if discovery["server"]["version"] != version:
        raise ValueError("Installed discovery belongs to another version")
    report = {
        "version": version,
        "source_sha": args.source_sha,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "live": args.live,
        "publication_performed": False,
        "descriptor_sha256": hashlib.sha256(
            (ROOT / "server.json").read_bytes()
        ).hexdigest(),
        "discovery_sha256": hashlib.sha256(args.discovery.read_bytes()).hexdigest(),
    }

    def unchecked():
        return providers.outcome("not_checked", "Live access was not requested")

    report["pypi"] = {name: unchecked() for name in expected}
    for name in ("official_registry", "glama", "smithery", "mcpfinder"):
        report[name] = unchecked()
    if args.live:
        for name, hashes in expected.items():
            report["pypi"][name] = checked(
                f"https://pypi.org/pypi/{name}/{version}/json",
                lambda payload, name=name, hashes=hashes: providers.pypi(
                    payload, name, version, hashes
                ),
            )
        report["official_registry"] = checked(
            "https://registry.modelcontextprotocol.io/v0.1/servers/"
            + quote(descriptor["name"], safe="")
            + "/versions/"
            + quote(version, safe=""),
            lambda payload: providers.official_registry(payload, descriptor),
        )
        # Automated authenticated reads use only the dedicated manual Actions
        # workflow's secrets. Local/ordinary CI never consumes directory keys.
        in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
        glama_key = os.environ.get("GLAMA_API_KEY") if in_actions else None
        report["glama"] = (
            checked(
                "https://glama.ai/api/mcp/v1/servers/Alien6-Studio/outerspace-apizr",
                lambda payload: providers.glama(payload, discovery),
                token=glama_key,
            )
            if glama_key
            else providers.outcome(
                "authentication_required",
                "GLAMA_API_KEY is absent; directory indexing is not_verified",
            )
        )
        smithery_key = os.environ.get("SMITHERY_API_KEY") if in_actions else None
        report["smithery"] = (
            inspect_smithery(
                args.smithery_name, smithery_key, discovery, args.smithery_bundle
            )
            if smithery_key
            else providers.outcome(
                "authentication_required",
                "SMITHERY_API_KEY is absent; listing is not_verified",
            )
        )
        report["mcpfinder"] = (
            live_snapshot(version)
            if args.include_mcpfinder
            else providers.outcome(
                "not_checked",
                "Use --include-mcpfinder for its bounded snapshot download",
            )
        )
    all_results = [
        *report["pypi"].values(),
        *(report[n] for n in ("official_registry", "glama", "smithery", "mcpfinder")),
    ]
    report["phase_b_complete"] = all(r["status"] == "verified" for r in all_results)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(
        "--candidate",
        type=Path,
        required=True,
        help="Qualified release-candidate candidate.json",
    )
    parser.add_argument(
        "--discovery",
        type=Path,
        required=True,
        help="Qualified installed analysis-only discovery JSON",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicit read-only external verification; never publication",
    )
    parser.add_argument(
        "--include-mcpfinder",
        action="store_true",
        help="Download a digest-bound snapshot, at most 128 MiB compressed / 512 MiB expanded",
    )
    parser.add_argument(
        "--smithery-name",
        help="Stable namespace/server chosen during separately authorized submission",
    )
    parser.add_argument(
        "--smithery-bundle",
        type=Path,
        help="Qualified reproducible MCPB for byte comparison with Smithery",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Exit nonzero while any external proof remains incomplete",
    )
    args = parser.parse_args(argv)
    report = verify(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        "Distribution evidence recorded; publication_performed=false; phase_b_complete="
        + str(report["phase_b_complete"]).lower()
    )
    return int(args.require_complete and not report["phase_b_complete"])


if __name__ == "__main__":
    raise SystemExit(main())

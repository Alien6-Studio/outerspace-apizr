"""Read-only release/PyPI preflight; this program never authenticates or publishes."""

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

from scripts.mcp_distribution.http import fetch_json
from scripts.mcp_distribution.metadata import (
    REPOSITORY,
    candidate_artifacts,
    read,
    validate_metadata,
)
from scripts.mcp_distribution.providers import pypi
from scripts.qualification.packaging.check_release_metadata import verify_public


def gh(path: str) -> dict:
    return json.loads(
        subprocess.check_output(["gh", "api", f"repos/{REPOSITORY}/{path}"], text=True)
    )


def validate_release(
    descriptor, source, tag, head, dirty, release, tagged, branch, comparison, candidate
):
    if not re.fullmatch(r"[0-9a-f]{40}", source) or tag != "v" + descriptor["version"]:
        raise ValueError(
            "Tag and full source SHA must identify this descriptor version"
        )
    if head != source or dirty:
        raise ValueError("Require an exact clean release checkout")
    if (
        release.get("tag_name") != tag
        or release.get("draft") is not False
        or release.get("prerelease") is not False
        or not release.get("published_at")
    ):
        raise ValueError("Require the already published final GitHub Release")
    if tagged.get("sha") != source or branch.get("protected") is not True:
        raise ValueError("Release tag and protected master identity are required")
    if (
        comparison.get("status") not in {"ahead", "identical"}
        or comparison.get("merge_base_commit", {}).get("sha") != source
    ):
        raise ValueError("Release source must belong to protected master history")
    assets = {a["name"]: a for a in release["assets"]}
    if (
        len(assets) != len(release["assets"])
        or not {
            "candidate.json",
            "public-comparison.json",
            "attest-verification.json",
            "release-assets.json",
        }
        <= assets.keys()
    ):
        raise ValueError("Release qualification assets are missing or ambiguous")
    expected = candidate_artifacts(candidate, descriptor["version"], source)
    for archives in expected.values():
        for filename, digest in archives.items():
            if assets.get(filename, {}).get("digest") != "sha256:" + digest:
                raise ValueError(
                    "GitHub release archives differ from the qualified candidate"
                )
    if candidate["schema"] == "apizr.release-candidate/v2":
        for item in [*candidate["artifacts"], *candidate.get("editor_evidence", [])]:
            if item["file"].startswith("editor/"):
                asset = assets.get(Path(item["file"]).name, {})
                if (
                    asset.get("digest") != "sha256:" + item["sha256"]
                    or asset.get("size") != item["bytes"]
                ):
                    raise ValueError(
                        "GitHub release VSIX evidence differs from the candidate"
                    )
    return expected


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    descriptor = validate_metadata()
    if (
        not re.fullmatch(r"[0-9a-f]{40}", args.source_sha)
        or args.release_tag != "v" + descriptor["version"]
    ):
        raise ValueError("Inputs must identify the exact descriptor version")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    if head != args.source_sha or dirty:
        raise ValueError("Require an exact clean release checkout")
    release = gh(f"releases/tags/{args.release_tag}")
    metadata = None
    with tempfile.TemporaryDirectory(prefix="apizr-registry-preflight-") as directory:
        subprocess.run(
            [
                "gh",
                "release",
                "download",
                args.release_tag,
                "--repo",
                REPOSITORY,
                "--pattern",
                "candidate.json",
                "--dir",
                directory,
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        expected = validate_release(
            descriptor,
            args.source_sha,
            args.release_tag,
            head,
            dirty,
            release,
            gh(f"commits/{args.release_tag}"),
            gh("branches/master"),
            gh(f"compare/{args.source_sha}...master"),
            read(Path(directory) / "candidate.json"),
        )
        if descriptor["version"] not in {"0.4.4", "0.4.5"}:
            subprocess.run(
                [
                    "gh",
                    "release",
                    "download",
                    args.release_tag,
                    "--repo",
                    REPOSITORY,
                    "--pattern",
                    "release-metadata.json",
                    "--dir",
                    directory,
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            dist = Path(directory) / "dist"
            candidate = read(Path(directory) / "candidate.json")
            if candidate.get("schema") == "apizr.release-candidate/v2":
                editor = Path(directory) / "editor"
                editor.mkdir()
                for item in [
                    *candidate["artifacts"],
                    *candidate.get("editor_evidence", []),
                ]:
                    if not item["file"].startswith("editor/"):
                        continue
                    name = Path(item["file"]).name
                    if item["file"] != "editor/" + name:
                        raise ValueError("Unexpected editor release asset path")
                    subprocess.run(
                        [
                            "gh",
                            "release",
                            "download",
                            args.release_tag,
                            "--repo",
                            REPOSITORY,
                            "--pattern",
                            name,
                            "--dir",
                            str(editor),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=60,
                    )
            subprocess.run(
                [
                    "gh",
                    "release",
                    "download",
                    args.release_tag,
                    "--repo",
                    REPOSITORY,
                    "--pattern",
                    "outerspace_apizr*",
                    "--dir",
                    str(dist),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
            metadata = verify_public(Path.cwd(), Path(directory), dist)
    results = {}
    for name, hashes in expected.items():
        payload, error = fetch_json(
            f"https://pypi.org/pypi/{name}/{descriptor['version']}/json"
        )
        if error or payload is None:
            raise ValueError("Public PyPI release evidence is unavailable")
        results[name] = pypi(payload, name, descriptor["version"], hashes)
        if results[name]["status"] != "verified":
            raise ValueError(
                "Public PyPI identity, ownership or archive digests differ"
            )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "version": descriptor["version"],
                "source_sha": args.source_sha,
                "tag": args.release_tag,
                "namespace": descriptor["name"],
                "pypi": results,
                "release_metadata": metadata,
                "preflight": "passed",
                "publication_performed": False,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        "Exact released source, archives and public PyPI verified; no publication performed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

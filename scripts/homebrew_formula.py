"""Render a local qualification tap or an explicitly verified immutable release tap."""

import argparse
import json
import re
import subprocess
import tarfile
from pathlib import Path

from homebrew_build_proof import candidate_source
from prepare_homebrew_build_inputs import digest, encoded, manifest
from prepare_release_assets import bound_file

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Alien6-Studio/outerspace-apizr"
VERSION = "0.4.2"
BUILD_MANIFEST = "925b8881feec75466ae489e7a0a71f9e97a2b7da0d6b75cdead210781009ea1b"


def publication_source(url, sha256, source, commit, candidate, evidence, bundle):
    """A URL and checksum alone cannot authorize publication-mode output."""
    expected = (
        f"https://github.com/{REPOSITORY}/releases/download/v{VERSION}/{source.name}"
    )
    if url != expected or sha256 != digest(source.read_bytes()):
        raise ValueError(
            "Expected exact immutable GitHub release URL and source SHA-256"
        )
    if evidence is None or bundle is None:
        raise ValueError("Signed release evidence and provenance bundle are required")
    subprocess.run(
        [
            "gh",
            "attestation",
            "verify",
            str(evidence),
            "--bundle",
            str(bundle),
            "--repo",
            REPOSITORY,
            "--signer-workflow",
            REPOSITORY + "/.github/workflows/ci.yml",
            "--source-digest",
            commit,
            "--source-ref",
            "refs/heads/release/0.4.2",
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    with tarfile.open(evidence) as archive:
        bound_file(
            archive,
            "coordinated/release-candidate/candidate.json",
            candidate / "candidate.json",
        )
        bound_file(archive, "coordinated/release-candidate/dist/" + source.name, source)
    release = json.loads(
        subprocess.check_output(
            ["gh", "api", f"repos/{REPOSITORY}/releases/tags/v{VERSION}"],
            timeout=60,
        )
    )
    assets = [a for a in release["assets"] if a["browser_download_url"] == url]
    if (
        release.get("immutable") is not True
        or release.get("draft") is not False
        or len(assets) != 1
        or assets[0].get("digest") != "sha256:" + sha256
        or assets[0].get("size") != source.stat().st_size
    ):
        raise ValueError(
            "Public immutable release asset does not match signed source bytes"
        )
    return url


def render(
    candidate,
    commit,
    output,
    *,
    mode,
    source_url=None,
    source_sha256=None,
    signed_evidence=None,
    provenance_bundle=None,
):
    if mode not in {"qualification", "publication"} or not re.fullmatch(
        r"[0-9a-f]{40}", commit
    ):
        raise ValueError("Explicit mode and exact source commit required")
    source, source_hash = candidate_source(candidate.resolve(), commit)
    inputs = manifest(ROOT / "uv.lock", ROOT / "policy/homebrew-build-inputs.json")
    if digest(encoded(inputs)) != BUILD_MANIFEST:
        raise ValueError("Reviewed build-input identity changed")
    if mode == "qualification":
        if any(
            x is not None
            for x in (source_url, source_sha256, signed_evidence, provenance_bundle)
        ):
            raise ValueError("Qualification uses only the exact local candidate")
        url = source.as_uri()
    else:
        url = publication_source(
            source_url,
            source_sha256,
            source,
            commit,
            candidate,
            signed_evidence,
            provenance_bundle,
        )
    resources = []
    for item in inputs["distributions"]:
        resources.append(
            f'  resource "{item["name"]}" do\n'
            f'    url "{item["url"]}", using: :nounzip\n'
            f'    sha256 "{item["sha256"]}"\n  end\n'
        )
    formula = (ROOT / "scripts/homebrew_formula.rb.in").read_text()
    for token, value in {
        "@SOURCE_URL@": json.dumps(url),
        "@SOURCE_SHA256@": source_hash,
        "@VERSION@": VERSION,
        "@BUILD_RESOURCES@": "\n".join(resources),
    }.items():
        formula = formula.replace(token, value)
    output.mkdir(parents=True, exist_ok=False)
    (output / "Formula").mkdir()
    (output / "Formula/apizr.rb").write_text(formula)
    (output / "README.md").write_text(
        "# Apizr Homebrew tap source\n\n"
        f"Generated in **{mode}** mode for core {VERSION}. Plugins remain separate.\n\n"
        "The public Alien6 tap is not yet published. The future command "
        "`brew install alien6-studio/tap/apizr` is pending and is not a working public installation route.\n\n"
        "Qualification targets Apple Silicon Tier-1 hosts, with hosted VM evidence identified separately. "
        "Intel macOS is Tier 3, not qualified and non-blocking. Linux Homebrew runtime is not qualified. "
        "Homebrew/core is not targeted. Online source audit is deferred until publication.\n"
    )
    receipt = {
        "schema": "apizr.homebrew-formula-source/v1",
        "mode": mode,
        "version": VERSION,
        "source_commit": commit,
        "source_sha256": source_hash,
        "formula_sha256": digest(formula.encode()),
        "build_inputs_manifest_sha256": BUILD_MANIFEST,
    }
    (output / "formula-source.json").write_bytes(encoded(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["qualification", "publication"], required=True
    )
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-url")
    parser.add_argument("--source-sha256")
    parser.add_argument("--signed-evidence", type=Path)
    parser.add_argument("--provenance-bundle", type=Path)
    args = parser.parse_args()
    render(
        args.candidate,
        args.source_sha,
        args.output,
        mode=args.mode,
        source_url=args.source_url,
        source_sha256=args.source_sha256,
        signed_evidence=args.signed_evidence,
        provenance_bundle=args.provenance_bundle,
    )


if __name__ == "__main__":
    main()

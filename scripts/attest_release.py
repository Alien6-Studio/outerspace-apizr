"""Bind verified release files to the managed Apizr identity; fail closed."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = {"schema", "consistency", "signature", "timestamp", "recompute"}


def validate_verdict(report: dict, expected_signer: str) -> None:
    checks = report.get("checks", [])
    if (
        report.get("verdict") != "pass"
        or report.get("signed_by") != expected_signer
        or report.get("warnings") != []
        or len(checks) != len(CHECKS)
        or {check.get("name") for check in checks} != CHECKS
        or any(check.get("status") != "pass" for check in checks)
    ):
        raise ValueError(
            "Receipt requires the Apizr signer and all five passing checks"
        )


def verify(
    attest: Path, workspace: Path, receipt: Path, trust: Path, expected_signer: str
) -> dict:
    result = subprocess.run(
        [
            str(attest),
            "verify",
            str(receipt),
            "--recompute",
            "--workspace",
            str(workspace),
            "--trust-store",
            str(trust),
            "--offline",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    report = json.loads(result.stdout)
    validate_verdict(report, expected_signer)
    return report


def copy_files(source: Path, destination: Path) -> dict[str, str]:
    """Only flat, regular artifact files enter the signed delivery directory."""
    files = sorted(source.iterdir())
    if not files:
        raise ValueError(f"Empty release artifacts: {source}")
    destination.mkdir(parents=True)
    hashes = {}
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Expected regular release artifact: {path.name}")
        target = destination / path.name
        shutil.copyfile(path, target)
        hashes[path.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    return hashes


def install_key(workspace: Path, key_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", key_id):
        raise ValueError("Invalid managed signing key identifier")
    private = os.environ.pop("APIZR_ATTEST_SIGNING_KEY", "")
    if not private.strip():
        raise ValueError(
            "APIZR_ATTEST_SIGNING_KEY is required; refusing unsigned delivery"
        )
    directory = workspace / ".attest/keys"
    directory.mkdir(mode=0o700)
    path = directory / f"{key_id}.key"
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(private)
    return path


def sign_delivery(attest: Path, workspace: Path, output: Path, policy: dict) -> None:
    key = install_key(workspace, policy["key_id"])
    try:
        subprocess.run(
            [
                str(attest),
                "run",
                "--pipeline",
                "attest.yaml",
                "--sign",
                "--timestamp",
                "--key",
                policy["key_id"],
                "--tsa",
                policy["tsa_url"],
            ],
            cwd=workspace,
            timeout=180,
            check=True,
        )
    finally:
        key.unlink(missing_ok=True)
    receipts = list((workspace / ".attest/receipts").glob("*.yaml"))
    if len(receipts) != 1:
        raise ValueError("Expected exactly one fresh release receipt")
    receipt = workspace / "receipt.yaml"
    shutil.copyfile(receipts[0], receipt)
    report = verify(
        attest, workspace, receipt, ROOT / ".attest/trust", policy["public_key_hex"]
    )
    output.mkdir(parents=True, exist_ok=False)
    (output / "attest-verification.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    # Explicit public allowlist: never archive keys, cache or the entire workspace.
    with tarfile.open(output / "apizr-attest-receipt.tar.gz", "w:gz") as archive:
        for name in ("attest.yaml", "receipt.yaml", "delivery"):
            archive.add(workspace / name, arcname=name)
        archive.add(ROOT / ".attest/trust", arcname="trust")
        archive.add(ROOT / "docs/contributing/attest.md", arcname="README.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attest", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--ci-run", required=True, type=int)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit) or args.ci_run <= 0:
        raise ValueError("Expected a source commit and positive verified CI run id")
    policy = tomllib.loads((ROOT / ".attest/release.toml").read_text())
    workspace = args.workspace.resolve()
    workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.copyfile(ROOT / ".attest/release.yaml", workspace / "attest.yaml")
    shutil.copytree(ROOT / ".attest/trust", workspace / ".attest/trust")
    distributions = copy_files(args.dist, workspace / "delivery/dist")
    evidence = copy_files(args.evidence, workspace / "delivery/evidence")
    if (
        len(distributions) != 2
        or sum(name.endswith(".whl") for name in distributions) != 1
        or sum(name.endswith(".tar.gz") for name in distributions) != 1
        or "ci-evidence.tar.gz" not in evidence
        or "build-provenance.sigstore.json" not in evidence
    ):
        raise ValueError("Missing verified distributions or build evidence")
    manifest = {
        "scope": "verified-release-delivery; not an Attest-supervised build",
        "repository": "Alien6-Studio/outerspace-apizr",
        "source_commit": args.commit,
        "ci_run_id": args.ci_run,
        "distributions": distributions,
        "evidence": evidence,
    }
    (workspace / "delivery/manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    sign_delivery(args.attest.resolve(), workspace, args.output, policy)


if __name__ == "__main__":
    main()

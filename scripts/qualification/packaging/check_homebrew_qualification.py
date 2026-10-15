"""Validate the explicit Homebrew host boundary separately from build identities."""

import argparse
import hashlib
import json
from pathlib import Path

QUALIFICATION = {
    "required": ["macos-arm64-tier1"],
    "not_qualified": [
        {"platform": "macos-x86_64", "reason": "homebrew-tier3"},
        {"platform": "linux", "reason": "runtime-not-qualified-in-0.4.3"},
    ],
}
EVIDENCE = {
    "ci": {"host": "virtual-machine", "runner": "macos-26"},
    "physical_mac": {"host": "physical-apple-silicon", "required": True},
}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def validate(policy, manifest_bytes):
    if (
        set(policy)
        != {
            "schema",
            "qualification",
            "evidence",
            "build_inputs_manifest_sha256",
        }
        or policy["schema"] != "apizr.homebrew-qualification/v1"
    ):
        raise ValueError("Unexpected Homebrew qualification schema")
    # This bounded release policy is deliberately exhaustive. Unknown, missing,
    # duplicate, contradictory or implicitly qualified hosts require review.
    if encoded(policy["qualification"]) != encoded(QUALIFICATION):
        raise ValueError("Unreviewed Homebrew platform qualification")
    if encoded(policy["evidence"]) != encoded(EVIDENCE):
        raise ValueError("Unreviewed Homebrew evidence boundary")
    if (
        hashlib.sha256(manifest_bytes).hexdigest()
        != policy["build_inputs_manifest_sha256"]
    ):
        raise ValueError("Homebrew build-input manifest identity changed")
    return {
        "schema": "apizr.homebrew-qualification-check/v1",
        "policy_sha256": hashlib.sha256(encoded(policy)).hexdigest(),
        "policy": policy,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = validate(json.loads(args.policy.read_text()), args.manifest.read_bytes())
    args.output.write_bytes(encoded(result))


if __name__ == "__main__":
    main()

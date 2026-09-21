"""Exercise real offline signature/timestamp/hash rejection with the pinned CLI."""

import argparse
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

import yaml
from attest_release import ROOT, verify


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attest", type=Path, required=True)
    args = parser.parse_args()
    attest = args.attest.resolve()
    policy = tomllib.loads((ROOT / ".attest/release.toml").read_text())
    fixture = ROOT / "tests/fixtures/attest-identity"
    trust = ROOT / ".attest/trust"
    verify(attest, fixture, fixture / "receipt.yaml", trust, policy["public_key_hex"])
    with tempfile.TemporaryDirectory(prefix="apizr-attest-check-") as temporary:
        workspace = Path(temporary) / "workspace"
        shutil.copytree(fixture, workspace)
        receipt = workspace / "receipt.yaml"
        original = yaml.safe_load(receipt.read_text())
        cases = ("changed-file", "missing-timestamp", "bad-signature", "untrusted-key")
        for case in cases:
            shutil.copyfile(
                fixture / "identity-check.txt", workspace / "identity-check.txt"
            )
            changed = dict(original)
            selected_trust = trust
            if case == "changed-file":
                (workspace / "identity-check.txt").write_text("changed after signing\n")
            elif case == "missing-timestamp":
                changed.pop("timestamp_token")
            elif case == "bad-signature":
                changed["signature"] = "00" * 64
            else:
                selected_trust = workspace / "empty-trust"
                selected_trust.mkdir()
            receipt.write_text(yaml.safe_dump(changed))
            try:
                verify(
                    attest, workspace, receipt, selected_trust, policy["public_key_hex"]
                )
            except (subprocess.CalledProcessError, ValueError):
                print(f"Rejected {case}")
            else:
                raise ValueError(f"Accepted invalid receipt: {case}")
    print("Managed identity, real RFC 3161 token and tamper rejection verified offline")


if __name__ == "__main__":
    main()

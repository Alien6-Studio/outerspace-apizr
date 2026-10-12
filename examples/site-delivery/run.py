"""Run the existing real registry fixture using public packages and scenario C."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--attest", action="store_true")
args = parser.parse_args()
source = Path(__file__).resolve().parent
output = args.output.resolve()
if output.exists() or output.is_relative_to(source):
    parser.error("choose a new evidence directory outside the extracted fixture")
if os.environ.get("APIZR_RELEASE_SET") or os.environ.get("APIZR_RELEASE_TARGET"):
    parser.error("this example uses public packages, not release candidate inputs")
with tempfile.TemporaryDirectory(prefix="apizr-delivery-example-") as temporary:
    fixture = Path(temporary) / "fixture"
    shutil.copytree(source, fixture)
    # This private fixture repository identifies test material, never a contribution.
    for command in (
        ["git", "init", "-q"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=Documentation fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Local fixture",
        ],
    ):
        subprocess.run(command, cwd=fixture, check=True, capture_output=True)
    subprocess.run(
        [
            sys.executable,
            str(fixture / "scripts/smoke_oci_registry.py"),
            "--public-packages",
            "--quote-example",
            "--output",
            str(output),
            *(["--attest"] if args.attest else []),
        ],
        check=True,
        cwd=fixture,
    )

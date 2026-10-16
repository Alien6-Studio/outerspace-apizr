"""Public-wheel preparation for the explicitly selected documentation fixture."""

import json
import os
import subprocess
import sys
from pathlib import Path


def copy_public_closure(name: str, destination: Path) -> bool:
    if os.environ.get("APIZR_DOCS_PUBLIC_PROOF") != "1":
        return False
    if os.environ.get("APIZR_RELEASE_SET") or os.environ.get("APIZR_RELEASE_TARGET"):
        raise ValueError(
            "Public documentation proof cannot consume candidate artifacts"
        )
    profiles = {
        "oci": ["outerspace-apizr==0.4.6", "outerspace-apizr-oci==0.4.6"],
        "attest": [
            "outerspace-apizr==0.4.6",
            "outerspace-apizr-oci==0.4.6",
            "outerspace-apizr-attest==0.4.6",
        ],
        "mcp": [
            "outerspace-apizr[preparation,mcp]==0.4.6",
            "outerspace-apizr-mcp==0.4.6",
        ],
    }
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--index-url",
            "https://pypi.org/simple",
            "--only-binary=:all:",
            "--dest",
            str(destination),
            *profiles[name],
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    (destination.parent / f"public-{name}-packages.json").write_text(
        json.dumps({"index": "https://pypi.org/simple", "requirements": profiles[name]})
        + "\n"
    )
    return True

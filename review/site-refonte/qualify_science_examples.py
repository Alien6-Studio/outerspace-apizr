"""Qualify the canonical science journey and the gallery's exact A/B commands."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from qualify_data_science_journey import (  # noqa: E402
    journey,
    network_guard,
    serving_checks,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--science-wheelhouse", type=Path, required=True)
    parser.add_argument("--runtime-target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    assert not output.exists() and not output.is_relative_to(ROOT)
    output.mkdir()
    archive = ROOT / "site/downloads/fraud-detection.zip"
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(output)
    project = output / "fraud-detection"
    shutil.copyfile(
        project / "data/transactions-a.csv", project / "data/transactions.csv"
    )
    python = args.python.absolute()
    serving = output / "serving/bin/python"
    network_guard(python, output / "network.log")
    result = journey(
        python,
        project,
        args.science_wheelhouse,
        args.runtime_target,
        output,
        serving_python=serving,
    )
    result["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    result["independent_transport_checks"] = serving_checks(
        python, serving, output / "bundles", output
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    env.update(
        PATH=str(python.parent) + os.pathsep + env["PATH"],
        SCIENCE_WHEELHOUSE=str(args.science_wheelhouse.resolve()),
        BUNDLES=str(output / "gallery-bundles"),
    )
    commands = {}
    for page, label in (
        ("compare-fraud", "compare"),
        ("share-prediction", "prediction"),
    ):
        markdown = (ROOT / "docs/examples" / (page + ".md")).read_text()
        matched = re.search(
            r"<!-- scenario:" + label + r" -->\s*```sh\n(.*?)```", markdown, re.S
        )
        assert matched is not None, "Missing documented scenario commands"
        block = matched.group(1)
        executed = subprocess.run(
            ["/bin/sh", "-eu", "-c", block],
            cwd=project,
            env=env,
            text=True,
            capture_output=True,
            timeout=120,
        )
        (output / (label + ".log")).write_text(executed.stdout + executed.stderr)
        assert executed.returncode == 0, executed.stdout + executed.stderr
        commands[label] = hashlib.sha256(block.encode()).hexdigest()
    comparison = json.loads((project / "comparison.json").read_text())
    assert comparison["data"][0]["content_state"] == "changed"
    result["gallery_commands_sha256"] = commands
    result["gallery_transports"] = serving_checks(
        python, serving, output / "gallery-bundles", output
    )
    (output / "public-proof.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

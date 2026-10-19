"""Read-only PyPI comparison and exact missing-file staging; never upload/build.

An existing filename is accepted only after its public bytes match the approved
archive. Network/authentication failures are not absence. No skip-existing mode.
"""

import argparse
import hashlib
import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path

PACKAGES = (
    "outerspace-apizr",
    "outerspace-apizr-oci",
    "outerspace-apizr-mcp",
    "outerspace-apizr-attest",
)


def public_files(name: str, version: str) -> dict:
    try:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{name}/{version}/json", timeout=30
        ) as response:
            data = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}
        raise
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("PyPI metadata exceeds bound")
    return {item["filename"]: item for item in json.loads(data)["urls"]}


def matches(path: Path, remote: dict) -> bool:
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    if remote["digests"]["sha256"] != expected or remote["size"] != path.stat().st_size:
        return False
    url = remote["url"]
    if not url.startswith("https://files.pythonhosted.org/"):
        raise ValueError("Unexpected public artifact host")
    size, digest = 0, hashlib.sha256()
    with urllib.request.urlopen(url, timeout=30) as response:
        while block := response.read(65536):
            size += len(block)
            if size > path.stat().st_size:
                return False
            digest.update(block)
    return size == path.stat().st_size and digest.hexdigest() == expected


def stage(dist: Path, output: Path, version: str) -> dict:
    expected = {
        name.replace("-", "_") + "-" + version + suffix
        for name in PACKAGES
        for suffix in ("-py3-none-any.whl", ".tar.gz")
    }
    if {p.name for p in dist.iterdir()} != expected:
        raise ValueError("Unexpected coordinated distributions")
    # Validate all four packages before creating any publication staging files.
    statuses = {}
    for name in PACKAGES:
        public = public_files(name, version)
        wanted = {
            filename
            for filename in expected
            if filename.startswith(name.replace("-", "_") + "-")
        }
        if set(public) - wanted:
            raise ValueError(f"Unexpected published files for {name}")
        states = {}
        for filename in sorted(wanted):
            if filename in public:
                if not matches(dist / filename, public[filename]):
                    raise ValueError(f"Published artifact differs: {filename}")
                states[filename] = "public-byte-identical"
            else:
                states[filename] = "pending"
        statuses[name] = states
    output.mkdir(parents=True, exist_ok=False)
    for name, states in statuses.items():
        directory = output / name
        directory.mkdir()
        for filename, state in states.items():
            if state == "pending":
                shutil.copyfile(dist / filename, directory / filename)
    (output / "public-comparison.json").write_text(
        json.dumps(statuses, indent=2) + "\n"
    )
    return statuses


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--github-output", type=Path)
    required = parser.add_mutually_exclusive_group()
    required.add_argument("--require-complete", action="store_true")
    required.add_argument("--require-package", choices=PACKAGES)
    args = parser.parse_args()
    statuses = stage(args.dist, args.output, args.version)
    if args.require_complete and any(
        "pending" in files.values() for files in statuses.values()
    ):
        raise ValueError("Publication remains incomplete")
    if args.require_package and "pending" in statuses[args.require_package].values():
        raise ValueError(f"Publication remains incomplete for {args.require_package}")
    if args.github_output:
        with args.github_output.open("a") as stream:
            for name, states in statuses.items():
                stream.write(
                    name.replace("-", "_")
                    + "="
                    + str("pending" in states.values()).lower()
                    + "\n"
                )


if __name__ == "__main__":
    main()

"""Deliberately build a local test worker image; never called by execution."""

import argparse
import json
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--base-image", default="python:3.14-slim")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # This preparation command explicitly permits base-image/dependency acquisition.
    # Execution receives only the final immutable image ID, never this mutable tag.
    lock = tomllib.loads((Path(__file__).parents[1] / "uv.lock").read_text())
    packages = {package["name"]: package for package in lock["package"]}
    selected = set()

    def collect(name):
        if name not in selected:
            selected.add(name)
            for dependency in packages[name].get("dependencies", []):
                collect(dependency["name"])

    collect("pydantic")
    requirements = []
    for name in sorted(selected):
        package = packages[name]
        hashes = sorted(
            {item["hash"] for item in [package["sdist"], *package["wheels"]]}
        )
        requirements.append(
            f"{name}=={package['version']} " + " ".join("--hash=" + h for h in hashes)
        )
    with tempfile.TemporaryDirectory(prefix="apizr-worker-image-") as directory:
        root = Path(directory)
        wheel = root / args.wheel.name
        shutil.copyfile(args.wheel, wheel)
        (root / "requirements.txt").write_text("\n".join(requirements) + "\n")
        (root / "Dockerfile").write_text(
            f"FROM {args.base_image}\n"
            "COPY requirements.txt /build/requirements.txt\n"
            "RUN pip install --no-cache-dir --require-hashes -r /build/requirements.txt\n"
            f"COPY {wheel.name} /build/{wheel.name}\n"
            f"RUN pip install --no-cache-dir --no-deps /build/{wheel.name} && rm -rf /build\n"
            'LABEL org.apizr.worker.protocol="apizr.runtime/v1"\n'
            'LABEL org.apizr.repository.worker.protocol="apizr.repository-runtime/v1"\n'
            "USER 65532:65532\n"
            'ENTRYPOINT ["/usr/local/bin/python", "-I", "-B", "-m", "apizr.oci.entrypoint"]\n'
        )
        identity = root / "image-id"
        subprocess.run(
            ["docker", "build", "--iidfile", str(identity), str(root)], check=True
        )
        image = identity.read_text().strip()
        inspected = json.loads(
            subprocess.check_output(["docker", "image", "inspect", image])
        )[0]
        args.output.write_text(
            json.dumps(
                {
                    "image": image,
                    "platform": inspected["Os"] + "/" + inspected["Architecture"],
                    "provider": "apizr.docker-engine/v1",
                },
                sort_keys=True,
            )
            + "\n"
        )
        print(args.output.read_text(), end="")


if __name__ == "__main__":
    main()

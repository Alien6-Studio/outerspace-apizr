"""Build the example container, exercise its API and remove the test container."""

import argparse
import json
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from src.main import convert


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python-version", help="Python version of the generated container"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    identifier = uuid.uuid4().hex[:12]
    image = f"apizr-smoke:{identifier}"
    container = None
    try:
        with tempfile.TemporaryDirectory(prefix="apizr-smoke-") as directory:
            project = Path(directory) / "project"
            convert(
                root / "examples/pricing.ipynb",
                project,
                python_version=args.python_version,
            )
            subprocess.run(
                ["docker", "build", "--tag", image, str(project)], check=True
            )
            container = run(
                "docker", "run", "--detach", "--publish", "127.0.0.1::5001", image
            )
            address = run("docker", "port", container, "5001/tcp").splitlines()[0]
            url = f"http://{address}"
            deadline = time.monotonic() + 60
            while True:
                try:
                    with urllib.request.urlopen(url + "/health", timeout=2) as response:
                        assert json.load(response) == {"status": "ok"}
                    break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Container did not become healthy")
                    time.sleep(0.5)
            request = urllib.request.Request(
                url + "/total",
                data=json.dumps({"prices": [10, 20]}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                assert response.status == 200
                assert json.load(response) == 36
            assert run("docker", "exec", container, "id", "-u") != "0"
            print(
                "Container smoke test passed: health, POST /total = 36, non-root user."
            )
    finally:
        if container:
            subprocess.run(["docker", "logs", container], check=False)
            subprocess.run(["docker", "rm", "--force", container], check=False)
        subprocess.run(["docker", "image", "rm", image], check=False)


if __name__ == "__main__":
    main()

"""Build the example container, exercise its API and remove the test container."""

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


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
            inputs = Path(directory) / "inputs"
            inputs.mkdir()
            notebook = json.loads((root / "examples/pricing.ipynb").read_text())
            notebook["cells"].append(
                {
                    "cell_type": "code",
                    "id": "delivery",
                    "metadata": {},
                    "execution_count": None,
                    "outputs": [],
                    "source": "def configuration_value() -> int:\n    from pathlib import Path\n    import json\n    from packaging.version import Version\n    return json.loads(Path('settings.json').read_text())['value'] + Version('2.0').major\n",
                }
            )
            source = inputs / "pricing.ipynb"
            source.write_text(json.dumps(notebook))
            (inputs / "settings.json").write_text('{"value": 5}')
            requirements = inputs / "requirements.txt"
            requirements.write_text("packaging>=24,<27\n")
            configuration = inputs / "config.yaml"
            configuration.write_text(
                "dockerizr:\n  server:\n    port: 5017\n  entrypoint: test -f settings.json\n"
            )
            command = [
                sys.executable,
                "-m",
                "apizr.cli",
                "--notebook",
                str(source),
                "--output-dir",
                str(project),
                "--configuration",
                str(configuration),
                "--requirements",
                str(requirements),
                "--include",
                "settings.json",
                "--build-image",
                image,
            ]
            if args.python_version:
                command += ["--python-version", args.python_version]
            result = json.loads(subprocess.check_output(command, text=True))
            assert result["image"]["tag"] == image
            assert result["image"]["id"] == run(
                "docker", "image", "inspect", "--format", "{{.Id}}", image
            )
            assert "settings.json" in result["files"]
            container = run(
                "docker", "run", "--detach", "--publish", "127.0.0.1::5017", image
            )
            address = run("docker", "port", container, "5017/tcp").splitlines()[0]
            url = f"http://{address}"
            deadline = time.monotonic() + 60
            while True:
                try:
                    with urllib.request.urlopen(url + "/health", timeout=2) as response:
                        assert json.load(response) == {"status": "ok"}
                    break
                except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Container did not become healthy") from exc
                    time.sleep(0.5)
            request = urllib.request.Request(
                url + "/total",
                data=json.dumps({"prices": [10, 20]}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                assert response.status == 200
                assert json.load(response) == 36
            with urllib.request.urlopen(
                urllib.request.Request(
                    url + "/configuration_value",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                ),
                timeout=5,
            ) as response:
                assert json.load(response) == 7
            assert run("docker", "exec", container, "id", "-u") != "0"
            print(
                "Container smoke test passed: one-command build, exact image identity, custom port/startup, explicit dependency/resource, POST /total = 36, non-root user."
            )
    finally:
        if container:
            subprocess.run(["docker", "logs", container], check=False)
            subprocess.run(["docker", "rm", "--force", container], check=False)
        subprocess.run(["docker", "image", "rm", image], check=False)


if __name__ == "__main__":
    main()

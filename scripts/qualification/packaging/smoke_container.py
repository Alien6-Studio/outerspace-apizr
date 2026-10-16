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
    root = Path(__file__).resolve().parents[3]
    identifier = uuid.uuid4().hex[:12]
    image = f"apizr-smoke:{identifier}"
    container = None
    try:
        with tempfile.TemporaryDirectory(prefix="apizr-smoke-") as directory:
            project = Path(directory).resolve() / "project"
            inputs = Path(directory).resolve() / "inputs"
            inputs.mkdir()
            source = inputs / "pricing.ipynb"
            source.write_bytes((root / "examples/pricing.ipynb").read_bytes())
            command = [
                sys.executable,
                "-m",
                "apizr.cli",
                "generate",
                "rest",
                str(source),
                "--select",
                "total",
                "--output-dir",
                str(project),
            ]
            result = json.loads(subprocess.check_output(command, text=True))
            assert {"app.py", "requirements.txt", "notebook.ipynb"} <= set(
                result["files"]
            )
            # This explicit test fixture builds an ordinary modern bundle. It is
            # qualification tooling, not a second application generator.
            version = args.python_version or "{}.{}".format(*sys.version_info[:2])
            from apizr.environment.python_target import parse_python_target

            parse_python_target(version)
            (project / "Dockerfile").write_text(
                f"FROM python:{version}-slim\n"
                "RUN python -m venv /opt/service\n"
                "COPY requirements.txt /service/requirements.txt\n"
                "RUN /opt/service/bin/pip install --no-cache-dir -r /service/requirements.txt\n"
                "COPY . /service\n"
                "WORKDIR /service\n"
                "USER 65532:65532\n"
                'CMD ["/opt/service/bin/python", "-B", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5017"]\n'
            )
            identity = inputs / "image-id"
            subprocess.run(
                [
                    "docker",
                    "build",
                    "--tag",
                    image,
                    "--iidfile",
                    str(identity),
                    str(project),
                ],
                check=True,
            )
            assert identity.read_text().strip() == run(
                "docker", "image", "inspect", "--format", "{{.Id}}", image
            )
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
                url + "/capabilities/total",
                data=json.dumps({"prices": [10, 20]}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                assert response.status == 200
                assert json.load(response) == 36
            assert run("docker", "exec", container, "id", "-u") != "0"
            print(
                "Container smoke test passed: modern notebook REST bundle, explicit target build, exact image identity, health, POST /capabilities/total = 36, non-root user."
            )
    finally:
        if container:
            subprocess.run(["docker", "logs", container], check=False)
            subprocess.run(["docker", "rm", "--force", container], check=False)
        subprocess.run(["docker", "image", "rm", image], check=False)


if __name__ == "__main__":
    main()

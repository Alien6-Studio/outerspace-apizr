"""Validate a built wheel and exercise its installed CLI outside the checkout."""

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "apizr/__init__.py" in names
        assert "apizr/capabilities/model.py" in names
        assert not any(name == "src.py" or name.startswith("src/") for name in names)
        assert any(name.endswith(".dist-info/licenses/LICENSE") for name in names)
        assert "apizr/modules/fast_apizr/generator/templates/fastApiApp.j2" in names
        assert "apizr/i18n/en/messages.json" in names
    notebook = Path(__file__).resolve().parents[1] / "examples/pricing.ipynb"
    with tempfile.TemporaryDirectory(prefix="apizr-wheel-") as directory:
        root = Path(directory)
        env = root / "env"
        subprocess.run(["uv", "venv", "--python", args.python, str(env)], check=True)
        bin_dir = env / ("Scripts" if sys.platform == "win32" else "bin")
        python = bin_dir / "python"
        cli = bin_dir / "apizr"
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), str(wheel)], check=True
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                """import apizr, importlib.util
from apizr.capabilities import inspect_source, canonical_bytes, document_digest
assert apizr.__file__
assert importlib.util.find_spec('src') is None
ir = inspect_source(b'def work(x: int) -> int: return x', module_name='installed')
assert ir.schema_version == 'apizr.capability/v1'
assert ir.capabilities[0].id == 'python:installed:work'
assert canonical_bytes(ir).endswith(b'\\n')
assert len(document_digest(ir).value) == 64
print(apizr.__file__)
""",
            ],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [str(cli), "--help"], cwd=root, check=True, stdout=subprocess.DEVNULL
        )
        result = subprocess.run(
            [
                str(cli),
                "--notebook",
                str(notebook),
                "--output-dir",
                str(root / "project"),
                "--force",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        manifest = json.loads(result.stdout)
        assert manifest["api_module"] == "pricing_api"
        assert {
            "pricing.py",
            "pricing.json",
            "pricing_api.py",
            "requirements.txt",
            "Dockerfile",
            "start.sh",
        } <= set(manifest["files"])
        for name in manifest["files"]:
            assert (root / "project" / name).is_file()
        print(
            "Wheel namespace, Capability IR, resources, license, CLI help and notebook generation passed."
        )


if __name__ == "__main__":
    main()

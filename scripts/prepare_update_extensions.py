"""Build trusted versions A/B and separate project locks without rebuilding later."""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

from smoke_extension_packaging import REPO, require_uv, run


def prepare(work: Path, uv: str, env: dict[str, str]) -> None:
    work.mkdir(parents=True, exist_ok=False)
    wheels = work / "wheels"
    wheels.mkdir()
    for version, value in (("1.0.0", 40), ("2.0.0", 71)):
        project = work / version
        project.mkdir()
        lines = []
        for folder, name in (
            ("leaf", "apizr-locked-leaf"),
            ("helper", "apizr-locked-helper"),
            ("plugin", "apizr-update-probe"),
        ):
            source = work / "sources" / version / folder
            shutil.copytree(REPO / "examples/extension-locked" / folder, source)
            toml = source / "pyproject.toml"
            toml.write_text(
                toml.read_text()
                .replace("1.0.0", version)
                .replace("apizr-locked-probe", "apizr-update-probe")
            )
            if folder == "plugin":
                manifest = source / "apizr-extension.json"
                data = json.loads(manifest.read_text())
                data.update(name=name, version=version)
                manifest.write_text(json.dumps(data))
            if folder == "leaf":
                (source / "src/apizr_locked_leaf/__init__.py").write_text(
                    f"VALUE = {value}\n"
                )
            run(
                [uv, "build", "--wheel", str(source), "--out-dir", str(wheels)],
                work,
                env,
            )
            wheel = wheels / f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            lines.append(f"{name}=={version} --hash=sha256:{digest}\n")
        (project / "requirements.lock").write_text("".join(lines))
        (project / "apizr.toml").write_text(
            f'schema_version="apizr.project/v1"\n[[plugins]]\nname="apizr-update-probe"\nversion="{version}"\nsha256="{digest}"\nrequirements="requirements.lock"\n'
        )
    (work / "user.toml").write_text(
        'schema_version="apizr.user/v1"\nplugins_dir="plugins"\n'
    )
    (work / "arguments.json").write_text("{}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    prepare(
        args.work_dir.resolve(),
        require_uv(),
        dict(os.environ, UV_PYTHON_DOWNLOADS="never"),
    )

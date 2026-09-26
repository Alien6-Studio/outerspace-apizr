"""Build two trusted closures once, with different shared dependency versions."""

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
    declarations = 'schema_version = "apizr.project/v1"\n'
    for suffix, version, value in [("a", "1.0.0", 40), ("b", "2.0.0", 71)]:
        name = f"apizr-sync-{suffix}"
        lines = []
        for folder, distribution in [
            ("leaf", "apizr-locked-leaf"),
            ("helper", "apizr-locked-helper"),
            ("plugin", name),
        ]:
            source = work / "sources" / suffix / folder
            shutil.copytree(REPO / "examples/extension-locked" / folder, source)
            toml = source / "pyproject.toml"
            content = toml.read_text().replace("1.0.0", version)
            if folder == "plugin":
                content = content.replace("apizr-locked-probe", name).replace(
                    f'version = "{version}"', 'version = "1.0.0"'
                )
                manifest = source / "apizr-extension.json"
                data = json.loads(manifest.read_text())
                data["name"] = name
                manifest.write_text(json.dumps(data))
            toml.write_text(content)
            if folder == "leaf":
                (source / "src/apizr_locked_leaf/__init__.py").write_text(
                    f"VALUE = {value}\n"
                )
            run(
                [uv, "build", "--wheel", str(source), "--out-dir", str(wheels)],
                work,
                env,
            )
            release = "1.0.0" if folder == "plugin" else version
            wheel = (
                wheels / f"{distribution.replace('-', '_')}-{release}-py3-none-any.whl"
            )
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            lines.append(f"{distribution}=={release} --hash=sha256:{digest}\n")
        requirements = f"{name}.lock"
        (work / requirements).write_text("".join(lines))
        declarations += (
            f'\n[[plugins]]\nname = "{name}"\nversion = "1.0.0"\n'
            f'sha256 = "{digest}"\nrequirements = "{requirements}"\n'
        )
    (work / "apizr.toml").write_text(declarations)
    (work / "user.toml").write_text(
        'schema_version = "apizr.user/v1"\nplugins_dir = "plugins"\n'
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

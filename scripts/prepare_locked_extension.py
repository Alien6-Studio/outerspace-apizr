"""Build the three trusted example wheels and emit their exact requirements lock."""

import argparse
import hashlib
import os
from pathlib import Path

from smoke_extension_packaging import REPO, require_uv, run


def prepare(wheelhouse: Path, uv: str, env: dict[str, str]) -> tuple[Path, str, Path]:
    wheelhouse.mkdir(parents=True, exist_ok=False)
    lines: list[str] = []
    for folder, name in (
        ("leaf", "apizr-locked-leaf"),
        ("helper", "apizr-locked-helper"),
        ("plugin", "apizr-locked-probe"),
    ):
        run(
            [
                uv,
                "build",
                "--wheel",
                str(REPO / "examples/extension-locked" / folder),
                "--out-dir",
                str(wheelhouse),
            ],
            wheelhouse.parent,
            env,
        )
        wheel = wheelhouse / f"{name.replace('-', '_')}-1.0.0-py3-none-any.whl"
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        lines.append(f"{name}==1.0.0 --hash=sha256:{digest}\n")
    lock = wheelhouse.parent / "requirements.lock"
    lock.write_text("".join(lines), encoding="utf-8")
    plugin = wheelhouse / "apizr_locked_probe-1.0.0-py3-none-any.whl"
    return plugin, hashlib.sha256(plugin.read_bytes()).hexdigest(), lock


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True, help="New directory")
    args = parser.parse_args()
    plugin, digest, lock = prepare(
        args.wheelhouse.resolve(),
        require_uv(),
        dict(os.environ, UV_PYTHON_DOWNLOADS="never"),
    )
    print(f"Wheel: {plugin}\nSHA-256: {digest}\nLock: {lock}")


if __name__ == "__main__":
    main()

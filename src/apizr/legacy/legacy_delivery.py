"""Explicit resources and local image builds for the notebook/script pipeline."""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PureWindowsPath


def resource_files(source_dir: Path, names: list[str]) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for name in names:
        relative = Path(name)
        if (
            not name
            or relative.is_absolute()
            or PureWindowsPath(name).is_absolute()
            or "\\" in name
            or any(part in {".", ".."} for part in name.split("/"))
        ):
            raise ValueError(
                "Included resources must be relative paths inside the source directory"
            )
        path = source_dir / relative
        if not path.exists():
            raise ValueError(f"Included resource does not exist: {name}")
        candidates = [path]
        if path.is_dir() and not path.is_symlink():
            candidates.extend(sorted(path.rglob("*")))
        for candidate in candidates:
            rel = candidate.relative_to(source_dir)
            for part in rel.parts:
                if part.startswith(".") or part == "__pycache__":
                    raise ValueError(f"Hidden/cache resources are not supported: {rel}")
            if any(
                (source_dir / Path(*rel.parts[:i])).is_symlink()
                for i in range(1, len(rel.parts) + 1)
            ):
                raise ValueError(f"Symlink resources are not supported: {rel}")
            if not candidate.resolve().is_relative_to(source_dir.resolve()):
                raise ValueError(f"Included resource escapes source directory: {rel}")
            if candidate.is_dir():
                continue
            if not candidate.is_file():
                raise ValueError(f"Included resource must be a regular file: {rel}")
            key = rel.as_posix()
            if key in files:
                raise ValueError(f"Repeated included resource: {key}")
            files[key] = candidate
    return files


def copy_resources(files: dict[str, Path], output: Path) -> None:
    # Check the complete destination set before copying; never replace generated files.
    for name in files:
        target = output / name
        if target.exists() or target.is_symlink():
            raise ValueError(
                f"Included resource collides with generated output: {name}"
            )
        for parent in target.parents:
            if parent == output:
                break
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise ValueError(f"Invalid included-resource destination: {name}")
    for name, source in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)


def validate_image_tag(tag: str) -> None:
    if len(tag) > 255 or not re.fullmatch(r"[a-z0-9][a-z0-9._/:-]*", tag):
        raise ValueError("Image tag must be a lowercase local Docker image reference")


def build_image(output: Path, tag: str) -> str:
    validate_image_tag(tag)
    with tempfile.TemporaryDirectory(prefix="apizr-image-") as temporary:
        iid = Path(temporary) / "image-id"
        try:
            subprocess.run(
                ["docker", "build", "--tag", tag, "--iidfile", str(iid), str(output)],
                check=True,
                stdout=sys.stderr,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Docker CLI is required for --build-image; install/start Docker or generate without this option"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Docker image build failed (exit {exc.returncode}); inspect the build log and retained output directory"
            ) from exc
        if not iid.is_file():
            raise RuntimeError("Docker build did not return an image identity")
        identity = iid.read_text().strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
            raise RuntimeError("Docker build returned an invalid image identity")
        return identity

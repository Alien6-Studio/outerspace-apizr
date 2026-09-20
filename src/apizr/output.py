"""Containment and exclusive creation for generated output files."""

from pathlib import Path, PurePosixPath, PureWindowsPath


def output_path(directory: Path | str, filename: str) -> Path:
    if (
        not filename
        or filename in {".", ".."}
        or PurePosixPath(filename).name != filename
        or PureWindowsPath(filename).name != filename
    ):
        raise ValueError("Expected an output filename without directory components")
    return Path(directory) / filename


def write_new_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    # Exclusive creation fails for existing files and dangling symlinks alike.
    with path.open("x", encoding=encoding) as output:
        output.write(content)

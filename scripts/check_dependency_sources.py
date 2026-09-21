"""Reject unreviewed dependency sources and unhashed distribution URLs."""

import re
import tomllib
from pathlib import Path
from urllib.parse import urlsplit


def validate_sources(lock: dict, project: str) -> None:
    for package in lock["package"]:
        source = package["source"]
        if package["name"] == project and source == {"editable": "."}:
            continue
        if source != {"registry": "https://pypi.org/simple"}:
            raise ValueError(f"Unapproved source for {package['name']}: {source}")
        archives = [*package.get("wheels", [])]
        if package.get("sdist"):
            archives.append(package["sdist"])
        if not archives:
            raise ValueError(f"No hashed distributions for {package['name']}")
        for archive in archives:
            url = urlsplit(archive.get("url", ""))
            if (
                url.scheme != "https"
                or url.netloc != "files.pythonhosted.org"
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", archive.get("hash", ""))
            ):
                raise ValueError(
                    f"Unapproved or unhashed archive for {package['name']}"
                )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]["name"]
    lock = tomllib.loads((root / "uv.lock").read_text())
    validate_sources(lock, project)
    print(f"Dependency source policy passed for {len(lock['package'])} locked entries")


if __name__ == "__main__":
    main()

"""Fail early on a new stable uv series or inconsistent development CI pins."""

import argparse
import ast
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_WORKFLOWS = {"publish-pypi.yml", "publish-mcp.yml"}


def policy(root: Path) -> tuple[tuple[tuple[int, int], ...], str]:
    source = ast.parse((root / "src/apizr/plugins/preparation/resolver.py").read_text())
    values = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in source.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"QUALIFIED_UV_SERIES", "QUALIFICATION_UV_VERSION"}
    }
    return values["QUALIFIED_UV_SERIES"], values["QUALIFICATION_UV_VERSION"]


def check(root: Path, latest: str) -> dict:
    series, pin = policy(root)
    match = re.fullmatch(r"(\d+)\.(\d+)\.\d+", latest)
    if match is None or (int(match[1]), int(match[2])) not in series:
        raise ValueError(
            f"uv {latest}: stable series is not qualified; run the native preparation proofs"
        )
    for path in (root / ".github/workflows").glob("*"):
        if path.name in PUBLICATION_WORKFLOWS or path.suffix not in {".yml", ".yaml"}:
            continue
        text = path.read_text()
        for value in re.findall(
            r"uses: astral-sh/setup-uv@[^\n]+\n\s+with:\n\s+version: ([^\n]+)",
            text,
        ):
            installed = value.strip().strip("'\"")
            if (
                path.name == "plugin-preparation-qualification.yml"
                and installed == "${{ matrix.uv }}"
            ):
                continue
            if installed != pin:
                raise ValueError(
                    f"{path.name}: uv {installed} differs from qualification pin {pin}"
                )
    return {
        "latest_stable": latest,
        "qualified_series": series,
        "qualification_pin": pin,
        "new_series_qualified": True,
        "development_ci_pins_consistent": True,
        "publication_workflows": "kept_separate_until_release_approval",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = urllib.request.Request(
        "https://api.github.com/repos/astral-sh/uv/releases/latest",
        headers={
            "User-Agent": "apizr-uv-qualification",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("uv release metadata exceeds qualification bound")
    latest = json.loads(raw)["tag_name"]
    report = check(ROOT, latest)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"uv {latest}: qualified series; development CI pin {report['qualification_pin']}"
    )


if __name__ == "__main__":
    main()

"""Select web-only checks from a complete Git diff; uncertainty runs product CI."""

import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

EXAMPLE_PAGES = {
    "docs/getting-started/introduction.md",
    "docs/getting-started/quickstart.md",
    "docs/getting-started/user-guide/exposure.md",
    "docs/development/0.4.md",
    "docs/reference/operator-policy.md",
}
MEDIA_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".mp4",
    ".webm",
}


def web_path(name: str) -> bool:
    path = PurePosixPath(name)
    if str(path) != name or path.is_absolute() or ".." in path.parts:
        return False
    if name.startswith("docs/") and path.suffix == ".md":
        return True
    if name.startswith(("docs/assets/images/", "docs/assets/videos/")):
        return path.suffix in MEDIA_SUFFIXES
    if name.startswith("docs/assets/stylesheets/") and path.suffix == ".css":
        return True
    if name.startswith("docs/assets/javascripts/") and path.suffix == ".js":
        return True
    return name.startswith("overrides/") and path.suffix == ".html"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], stderr=subprocess.PIPE, timeout=60)


def changed_files(base: str, head: str) -> list[tuple[str, str, str]]:
    # No rename detection: both sides of a move must qualify for the web path.
    # Raw NUL records preserve unusual filenames and expose symlinks/submodules.
    raw = git("diff", "--no-ext-diff", "--no-renames", "--raw", "-z", base, head, "--")
    if not raw:
        return []
    records = raw.removesuffix(b"\0").split(b"\0")
    if len(records) % 2:
        raise ValueError("Incomplete Git diff")
    result = []
    for header, name in zip(records[::2], records[1::2], strict=True):
        old_mode, new_mode, _, _, status = header.decode("ascii").split()
        if not old_mode.startswith(":") or status not in {"A", "D", "M", "T"}:
            raise ValueError("Unexpected Git diff record")
        result.append((name.decode("utf-8"), old_mode[1:], new_mode))
    return result


def classify(event_name: str, event: dict) -> dict[str, str]:
    full = {"product": "true", "examples": "true", "reason": "Full qualification"}
    if event_name not in {"pull_request", "push"}:
        return full | {"reason": "Manual, scheduled or unsupported event"}
    try:
        if event_name == "pull_request":
            if event["pull_request"]["base"]["ref"] != "master":
                return full
            base = event["pull_request"]["base"]["sha"]
            head = event["pull_request"]["head"]["sha"]
        else:
            if event["ref"] != "refs/heads/master":
                return full
            base, head = event["before"], event["after"]
        if any(
            not isinstance(sha, str)
            or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or sha == "0" * 40
            for sha in (base, head)
        ):
            raise ValueError("Missing comparison commits")
        if event_name == "pull_request":
            base = git("merge-base", base, head).decode("ascii").strip()
        changes = changed_files(base, head)
        if not changes or any(
            not web_path(name)
            or old not in {"000000", "100644"}
            or new not in {"000000", "100644"}
            for name, old, new in changes
        ):
            return full
        examples = any(name in EXAMPLE_PAGES for name, _, _ in changes)
        return {
            "product": "false",
            "examples": str(examples).lower(),
            "reason": "Only allowlisted web content changed",
        }
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
        return full | {"reason": "Comparison unavailable; full qualification required"}


def main() -> None:
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        if not isinstance(event, dict):
            raise ValueError("Invalid event")
    except (KeyError, ValueError, OSError):
        event = {}
    result = classify(os.environ.get("GITHUB_EVENT_NAME", ""), event)
    output = "".join(f"{key}={value}\n" for key, value in result.items())
    print(output, end="")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
        stream.write(output)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as stream:
            stream.write(
                f"{result['reason']}. Product checks: **{result['product']}**; "
                f"documentation examples: **{result['examples']}**.\n"
            )


if __name__ == "__main__":
    main()

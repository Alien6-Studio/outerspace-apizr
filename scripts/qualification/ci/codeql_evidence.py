"""Use exact native CodeQL evidence where covered; retain scans on other refs."""

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

LANGUAGES = {"python", "javascript-typescript", "actions"}
NATIVE = "dynamic/github-code-scanning/codeql:analyze"


def github(repository, path, *, pages=False, sarif=False):
    endpoint = f"repos/{repository}" + ("/" + path if path else "")
    command = ["gh", "api", endpoint]
    if pages:
        command += ["--paginate", "--slurp"]
    if sarif:
        command += ["--header", "Accept: application/sarif+json"]
    return json.loads(subprocess.check_output(command, text=True, timeout=60))


def selection(environment):
    repository = environment["GITHUB_REPOSITORY"]
    commit, ref = environment["GITHUB_SHA"], environment["GITHUB_REF"]
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository) or not re.fullmatch(
        r"[0-9a-f]{40}", commit
    ):
        raise ValueError("Exact GitHub repository and source commit required")
    # Default-setup configuration requires administration:read, unavailable to
    # GITHUB_TOKEN. Coverage is selected from public branch metadata; covered refs
    # must then supply exact successful native analyses for all three languages.
    default = github(repository, "")["default_branch"]
    event = environment["GITHUB_EVENT_NAME"]
    branch = (
        environment.get("GITHUB_BASE_REF", "")
        if event == "pull_request"
        else ref.removeprefix("refs/heads/")
    )
    native = branch == default
    if (
        not native
        and branch
        and (event == "pull_request" or ref.startswith("refs/heads/"))
    ):
        native = (
            github(repository, "branches/" + quote(branch, safe="")).get("protected")
            is True
        )
    if event == "pull_request" and not re.fullmatch(r"refs/pull/[1-9]\d*/merge", ref):
        raise ValueError("Require the exact pull-request merge ref")
    return {
        "repository": repository,
        "commit": commit,
        "ref": ref,
        "mode": "native" if native else "retained",
        "languages": sorted(LANGUAGES),
    }


def native_records(records, selected, now):
    latest = {}
    for item in records:
        language = item.get("category", "").removeprefix("/language:")
        if (
            item.get("commit_sha") != selected["commit"]
            or item.get("ref") != selected["ref"]
            or item.get("analysis_key") != NATIVE
            or language not in LANGUAGES
        ):
            continue
        if language not in latest or item["id"] > latest[language]["id"]:
            latest[language] = item
    for item in latest.values():
        if item.get("error"):
            raise ValueError(
                "Latest native CodeQL analysis failed: " + item["category"]
            )
        created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        if not now - timedelta(days=8) <= created <= now + timedelta(minutes=5):
            raise ValueError(
                "Native CodeQL evidence is outside its weekly freshness window"
            )
    return (
        [latest[name] for name in sorted(LANGUAGES)]
        if latest.keys() == LANGUAGES
        else None
    )


def retain_native(selected, output, timeout):
    deadline = time.monotonic() + timeout
    query = urlencode({"ref": selected["ref"], "tool_name": "CodeQL", "per_page": 100})
    while True:
        pages = github(
            selected["repository"], "code-scanning/analyses?" + query, pages=True
        )
        records = native_records(
            [item for page in pages for item in page],
            selected,
            datetime.now(timezone.utc),
        )
        if records is not None:
            break
        if time.monotonic() >= deadline:
            raise ValueError("Missing exact-source native CodeQL analyses")
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    for item in records:
        sarif = github(
            selected["repository"], f"code-scanning/analyses/{item['id']}", sarif=True
        )
        runs = sarif.get("runs", [])
        if not runs or any(
            not any(
                p.get("revisionId") == selected["commit"]
                for p in run.get("versionControlProvenance", [])
            )
            or any(
                invocation.get("executionSuccessful") is False
                for invocation in run.get("invocations", [])
            )
            for run in runs
        ):
            raise ValueError("Native SARIF source or execution mismatch")
        language = item["category"].removeprefix("/language:")
        (output / (language + ".sarif")).write_text(json.dumps(sarif) + "\n")
    report = {
        **selected,
        "result": "pass",
        "analyses": records,
        "duplicate_analysis_started": False,
    }
    (output / "native-evidence.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("select", "native"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if not 0 <= args.timeout <= 900:
        parser.error("--timeout must be between zero and 900 seconds")
    selected = selection(os.environ)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "selection.json").write_text(json.dumps(selected, indent=2) + "\n")
    if args.operation == "native":
        if selected["mode"] != "native":
            raise ValueError("This ref requires its retained explicit CodeQL scan")
        retain_native(selected, args.output, args.timeout)
    if args.github_output:
        with args.github_output.open("a") as stream:
            stream.write("mode=" + selected["mode"] + "\n")
    print(json.dumps(selected))


if __name__ == "__main__":
    main()

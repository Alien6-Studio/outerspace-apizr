"""Require an explicit DCO declaration for new contributions in a Git range."""

import argparse
import re
import subprocess

# This release-preparation commit predates the maintainer's DCO decision.
# An immutable exception avoids rewriting already-reviewed history.
PRE_ADOPTION = {"553337347f4fd2f5babcdc812bb7547c4184ef1f"}


def trailers(message: str) -> list[str]:
    return subprocess.check_output(
        ["git", "interpret-trailers", "--parse"], input=message, text=True
    ).splitlines()


def validate(commits: list[dict]) -> None:
    """A responsible submitter may explicitly certify earlier commits too.

    This checks declarations, not the truth of authorship or license rights.
    No bot-name, maintainer-membership or cryptographic-signature exemption.
    """
    by_sha = {c["sha"]: c for c in commits}
    certified = set(PRE_ADOPTION)
    for commit in commits:
        lines = trailers(commit["message"])
        identity = f"{commit['name']} <{commit['email']}>"
        signed = any(
            key.lower() == "signed-off-by" and value.strip() == identity
            for line in lines
            for key, _, value in [line.partition(":")]
        )
        references = [
            value.strip()
            for line in lines
            for key, _, value in [line.partition(":")]
            if key.lower() == "dco-sign-off-for"
        ]
        if signed:
            certified.add(commit["sha"])
        if references and not signed:
            raise ValueError("A DCO remediation must carry its submitter's sign-off")
        for sha in references:
            if not re.fullmatch(r"[0-9a-f]{40}", sha) or sha not in by_sha:
                raise ValueError(
                    f"DCO remediation references no commit in this range: {sha}"
                )
            certified.add(sha)
    missing = sorted(set(by_sha) - certified)
    if missing:
        raise ValueError(
            "Missing DCO sign-off for: "
            + ", ".join(missing)
            + ". See CONTRIBUTING.md; do not add another person's declaration."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    for ref in (args.base, args.head):
        if not re.fullmatch(r"[0-9a-f]{40}", ref) and ref != "HEAD":
            parser.error("Expected full Git object IDs (or HEAD)")
    shas = subprocess.check_output(
        ["git", "rev-list", "--no-merges", f"{args.base}..{args.head}"], text=True
    ).splitlines()
    commits = []
    for sha in shas:
        name, email, message = subprocess.check_output(
            ["git", "show", "-s", "--format=%an%x00%ae%x00%B", sha], text=True
        ).split("\0", 2)
        commits.append({"sha": sha, "name": name, "email": email, "message": message})
    validate(commits)
    print(f"DCO declarations verified for {len(commits)} non-merge commits")


if __name__ == "__main__":
    main()

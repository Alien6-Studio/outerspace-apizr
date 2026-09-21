"""Check the reviewed universal dependency inventory; never infer approval."""

import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path

from packaging.licenses import canonicalize_license_expression
from packaging.utils import canonicalize_name

SCOPE = "locked-dependency-use-with-upstream-notices"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def distribution_fingerprint(package: dict) -> str:
    """Bind the review to the complete archive set, including other platforms."""
    archives = [*package.get("wheels", [])]
    if package.get("sdist"):
        archives.append(package["sdist"])
    value = {
        "source": package["source"],
        "archives": sorted((a["url"], a["hash"]) for a in archives),
    }
    return digest(json.dumps(value, sort_keys=True).encode())


def license_allowed(expression: str, allowed: set[str]) -> bool:
    """Evaluate SPDX AND/OR/parentheses after packaging validates the grammar.

    WITH is an indivisible license/exception pair, never blanket permission for
    either term. Parsing consumes both branches even when the result is known.
    """
    normalized = canonicalize_license_expression(expression)
    tokens = re.findall(r"\(|\)|[^\s()]+", normalized)
    position = 0

    def atom() -> bool:
        nonlocal position
        token = tokens[position]
        position += 1
        if token == "(":
            result = disjunction()
            if tokens[position] != ")":
                raise ValueError("Unbalanced license expression")
            position += 1
            return result
        if position < len(tokens) and tokens[position] == "WITH":
            token += " WITH " + tokens[position + 1]
            position += 2
        return token in allowed

    def conjunction() -> bool:
        nonlocal position
        result = atom()
        while position < len(tokens) and tokens[position] == "AND":
            position += 1
            right = atom()
            result = result and right
        return result

    def disjunction() -> bool:
        nonlocal position
        result = conjunction()
        while position < len(tokens) and tokens[position] == "OR":
            position += 1
            right = conjunction()
            result = result or right
        return result

    result = disjunction()
    if position != len(tokens):
        raise ValueError("Unconsumed license expression")
    return result


def validate_inventory(lock: dict, inventory: dict, policy: dict, texts: dict) -> dict:
    if any(x.get("schema_version") != 1 for x in (inventory, policy, texts)):
        raise ValueError("Unsupported license policy schema")
    if inventory.get("scope") != SCOPE or policy.get("scope") != SCOPE:
        raise ValueError("Unreviewed license policy scope")
    packages = []
    for package in lock["package"]:
        if package["name"] == "outerspace-apizr" and package["source"] == {
            "editable": "."
        }:
            continue
        if package["source"] != {"registry": "https://pypi.org/simple"}:
            raise ValueError(f"Unreviewed dependency source: {package['name']}")
        packages.append(package)
    expected = {(p["name"], p["version"]): p for p in packages}
    reviews = inventory["packages"]
    reviewed = {(r["name"], r["version"]): r for r in reviews}
    if (
        len(expected) != len(packages)
        or len(reviewed) != len(reviews)
        or set(expected) != set(reviewed)
    ):
        raise ValueError("License inventory does not exactly cover the universal lock")
    denied = {canonicalize_name(p["name"]): p for p in policy["denied_packages"]}
    allowed = set(policy["allowed_licenses"])
    exceptions = policy["exceptions"]
    used_exceptions = set()
    referenced_texts = set()
    for key, package in expected.items():
        name, version = key
        if canonicalize_name(name) in denied:
            raise ValueError(
                f"Denied package {name}: {denied[canonicalize_name(name)]['reason']}"
            )
        review = reviewed[key]
        if review.get("status") != "reviewed" or not review.get("notes", "").strip():
            raise ValueError(f"Missing license review for {name}")
        if review.get("distribution_fingerprint") != distribution_fingerprint(package):
            raise ValueError(f"Distributions changed since license review: {name}")
        archive = review["evidence_archive"]
        locked_archives = [*package.get("wheels", []), package.get("sdist", {})]
        if not any(
            a.get("url") == archive["url"] and a.get("hash") == archive["hash"]
            for a in locked_archives
        ):
            raise ValueError(f"License evidence is not from a locked archive: {name}")
        files = review["license_files"]
        if not files or len({f["path"] for f in files}) != len(files):
            raise ValueError(f"Missing or duplicate license evidence: {name}")
        for file in files:
            value = texts["texts"].get(file["sha256"])
            if value is None or digest(value.encode("utf-8")) != file["sha256"]:
                raise ValueError(
                    f"Missing or altered license text: {name}/{file['path']}"
                )
            referenced_texts.add(file["sha256"])
        scoped_allowed = set(allowed)
        for index, exception in enumerate(exceptions):
            if (exception["name"], exception["version"]) == key:
                if not exception.get("reason", "").strip() or not exception.get(
                    "evidence_sha256"
                ):
                    raise ValueError(f"Unjustified license exception: {name}")
                if not set(exception["evidence_sha256"]) <= {
                    f["sha256"] for f in files
                }:
                    raise ValueError(f"Exception lacks evidence: {name}")
                scoped_allowed.update(exception["licenses"])
                used_exceptions.add(index)
        # Components are cumulative. OR is a choice only inside one expression.
        for component in review["components"]:
            if not component.get("scope", "").strip() or not component.get(
                "evidence_sha256"
            ):
                raise ValueError(f"Unscoped license component: {name}")
            if not set(component["evidence_sha256"]) <= {f["sha256"] for f in files}:
                raise ValueError(f"Component lacks evidence: {name}")
            if not license_allowed(component["expression"], scoped_allowed):
                raise ValueError(
                    f"Unapproved license for {name}: {component['expression']}"
                )
        if not review["components"]:
            raise ValueError(f"Missing license expression: {name}")
    if used_exceptions != set(range(len(exceptions))):
        raise ValueError("Stale license exception; remove it or review the new version")
    if referenced_texts != set(texts["texts"]):
        raise ValueError("Unreferenced license evidence")
    return {
        "schema": "apizr.dependency-license-report/v1",
        "result": "pass",
        "scope": SCOPE,
        "packages": len(expected),
        "license_texts": len(referenced_texts),
        "exceptions": len(used_exceptions),
        "limitations": inventory["limitations"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files = {
        "lock": root / "uv.lock",
        "inventory": root / "policy/dependency-licenses.json",
        "policy": root / "policy/dependency-policy.json",
        "texts": root / "policy/dependency-license-texts.json",
    }
    report = validate_inventory(
        tomllib.loads(files["lock"].read_text()),
        *(
            json.loads(files[name].read_text())
            for name in ("inventory", "policy", "texts")
        ),
    )
    report["inputs"] = {
        str(path.relative_to(root)): digest(path.read_bytes())
        for path in files.values()
    }
    result = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(result)
    print(result, end="")


if __name__ == "__main__":
    main()

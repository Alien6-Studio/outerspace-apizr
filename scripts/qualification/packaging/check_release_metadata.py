"""Freeze release-facing source before building; verify retained README/metadata bytes."""

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REPOSITORY = "https://github.com/Alien6-Studio/outerspace-apizr"
PROJECTS = (".", "plugins/oci", "plugins/attest", "plugins/mcp")
POLICY = "policy/release-metadata.toml"
VERSION = r"\d+\.\d+\.\d+(?:rc[1-9]\d*)?"
URLS = {
    "Repository": REPOSITORY,
    "Documentation": "https://apizr.outerspace.sh/",
    "Issues": REPOSITORY + "/issues",
    "Changelog": REPOSITORY + "/blob/v{version}/CHANGELOG.md",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(version):
    return sorted(
        {
            POLICY,
            "README.md",
            "pyproject.toml",
            "docs/getting-started/install.md",
            f"docs/releases/{version}.md",
            "Dockerfile",
            "glama.json",
            "action.yml",
            "templates/apizr.yml",
            "SECURITY.md",
            "examples/data-science/fraud-detection/README.md",
            "examples/governance/README.md",
            "server.json",
            "CHANGELOG.md",
            "docs/index.md",
            "mkdocs.yml",
            "plugins/mcp/distribution/manifest.json",
            "plugins/mcp/distribution/pyproject.toml",
            *(
                f"plugins/{name}/{file}"
                for name in ("oci", "attest", "mcp")
                for file in ("pyproject.toml", "README.md", "apizr-extension.json")
            ),
        }
    )


def reference(root):
    # A PR into development can qualify; tags, master and release/* cannot use
    # the inherited-version exception. Explicit --release always refuses it.
    ref = os.environ.get("GITHUB_REF")
    if ref and ref.startswith("refs/pull/"):
        return "refs/heads/" + os.environ.get("GITHUB_BASE_REF", "")
    if ref:
        return ref
    return subprocess.check_output(
        ["git", "symbolic-ref", "--quiet", "HEAD"], cwd=root, text=True, timeout=10
    ).strip()


def stated_versions(text):
    plain = text.replace("**", "").replace("`", "")
    patterns = (
        rf"outerspace[-_]apizr(?:[-_](?:oci|mcp|attest))?(?:\[[^\]\n]+\])?(?:==|@|-|\s+)({VERSION})",
        rf"\b(?:Apizr|published|stable|release|candidate)\s+({VERSION})\b",
        rf"\(({VERSION})\)",
        rf"/(?:releases|tree|blob)/(?:v)?({VERSION})(?=[/#.\s)]|$)",
        rf"APIZR_VERSION:-({VERSION})",
        rf"apizr-({VERSION})-",
    )
    return {value for pattern in patterns for value in re.findall(pattern, plain)}


def check(root=ROOT, *, release=False, ref=None):
    root = root.resolve()
    policy = tomllib.loads((root / POLICY).read_text())
    if policy.get("schema_version") != 1:
        raise ValueError("Unsupported release metadata policy")
    target = policy["release"]["version"]
    if re.fullmatch(VERSION, target) is None:
        raise ValueError("Invalid release metadata version")
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    development = policy.get("development")
    if development:
        if (
            release
            or (ref or reference(root)) != "refs/heads/" + development["branch"]
            or version != development["package_version"]
            or version == target
            or development["branch"] != target
            or not development.get("reason")
        ):
            raise ValueError(
                "Development metadata marker cannot authorize this release/ref/version"
            )
        public = development["published_version"]
    else:
        if version != target:
            raise ValueError("Release metadata disagrees with pyproject.toml")
        public = version
    errors, descriptions = [], []
    for directory in PROJECTS:
        project_root = root / directory
        project = tomllib.loads((project_root / "pyproject.toml").read_text())[
            "project"
        ]
        if project["version"] != version:
            errors.append(f"{directory}/pyproject.toml: uncoordinated version")
        expected_urls = {
            key: value.format(version=public) for key, value in URLS.items()
        }
        if any(
            project.get("urls", {}).get(key) != value
            for key, value in expected_urls.items()
        ):
            errors.append(f"{directory}/pyproject.toml: missing/stale Project URLs")
        if directory != ".":
            name = project["name"]
            manifest = json.loads((project_root / "apizr-extension.json").read_text())
            if manifest["version"] != version or manifest["name"] != name:
                errors.append(
                    f"{directory}/apizr-extension.json: uncoordinated version"
                )
            for dependency in (
                "outerspace-apizr-oci"
                if name.endswith("attest")
                else "outerspace-apizr",
            ):
                if dependency + "==" + version not in project["dependencies"]:
                    errors.append(f"{directory}/pyproject.toml: stale {dependency} pin")
        readme = project_root / project["readme"]
        descriptions.append(readme.relative_to(root).as_posix())
    descriptions.append("docs/getting-started/install.md")
    for name in descriptions:
        text = (root / name).read_text()
        allowed = {public, target} if development else {version}
        wrong = stated_versions(text) - allowed
        if wrong:
            errors.append(f"{name}: stale Apizr statements {sorted(wrong)}")
        if development:
            if f"<!-- apizr-development: {target} -->" not in text:
                errors.append(f"{name}: missing explicit development marker")
        elif re.search(
            r"apizr-development:|not (?:yet )?published|release candidate|future .*listing",
            text,
            re.I,
        ):
            errors.append(
                f"{name}: development/candidate wording in release description"
            )
        for branch in re.findall(
            re.escape(REPOSITORY) + r"/(?:tree|blob)/([^/]+)/", text
        ):
            if branch != "v" + public and not (development and branch == target):
                # Immutable illustration/demo source commits are historical assets.
                if not re.fullmatch(r"[0-9a-f]{40}", branch):
                    errors.append(f"{name}: source link must use immutable v{public}")
        if name.endswith("README.md") and public not in stated_versions(text):
            errors.append(f"{name}: missing current Apizr version")
    descriptor = json.loads((root / "server.json").read_text())
    if descriptor["version"] != version or any(
        p["version"] != version for p in descriptor["packages"]
    ):
        errors.append("server.json: stale descriptor/package version")
    launcher = root / "plugins/mcp/distribution"
    launcher_project = tomllib.loads((launcher / "pyproject.toml").read_text())[
        "project"
    ]
    if (
        launcher_project["version"] != version
        or f"outerspace-apizr-mcp=={version}" not in launcher_project["dependencies"]
        or json.loads((launcher / "manifest.json").read_text())["version"] != version
    ):
        errors.append("MCP distribution: stale launcher/wrapper version")
    # Read the scalar directly; the metadata gate needs only the standard library.
    action = (root / "action.yml").read_text()
    match = re.search(
        r"^  apizr-version:\n(?:    [^\n]*\n)*?    default: ['\"]?([^\s'\"]+)",
        action,
        re.M,
    )
    if match is None or match[1] != public:
        errors.append("action.yml: stale public apizr-version default")
    component = (root / "templates/apizr.yml").read_text()
    match = re.search(
        r"^    apizr-version:\n(?:      [^\n]*\n)*?      default: ['\"]?([^\s'\"]+)",
        component,
        re.M,
    )
    if match is None or match[1] != public:
        errors.append("templates/apizr.yml: stale apizr-version default")
    docker = (root / "Dockerfile").read_text()
    expected_ref = target if development else "v" + version
    if (
        re.findall(r"^ARG SOURCE_REF=(.+)$", docker, re.M) != [expected_ref]
        or '--branch "$SOURCE_REF"' not in docker
    ):
        errors.append("Dockerfile: source ref must identify the qualified release")
    glama = json.loads((root / "glama.json").read_text())
    if glama.get(
        "$schema"
    ) != "https://glama.ai/mcp/schemas/server.json" or not glama.get("maintainers"):
        errors.append("glama.json: missing retained ownership contract")
    # The retained Glama schema has no version property. Bind the descriptor bytes
    # with the recipe and qualified source instead of inventing a version field.
    if not re.search(
        r"^## " + re.escape(target) + r"(?:\s|$)",
        (root / "CHANGELOG.md").read_text(),
        re.M,
    ):
        errors.append("CHANGELOG.md: missing target release entry")
    if not re.search(
        r"^# " + re.escape(target) + r"(?:\s|$)",
        (root / f"docs/releases/{target}.md").read_text(),
        re.M,
    ):
        errors.append("Release record does not identify the target version")
    if errors:
        raise ValueError("Release metadata refused:\n" + "\n".join(errors))
    return {
        "schema": "apizr.release-metadata/v1",
        "version": version,
        "target_version": target,
        "mode": "development" if development else "release",
        "release_metadata_ready": not bool(development),
        "publication_performed": False,
        "files": [
            {"path": name, "sha256": sha((root / name).read_bytes())}
            for name in inventory(target)
        ],
    }


def verify_snapshot(root, snapshot, *, release=False):
    current = check(root, release=release)
    if snapshot != current:
        raise ValueError(
            "Release-facing source changed after candidate build; build a new candidate"
        )
    return current


def verify_archives(root, dist):
    """Compare the actual frozen metadata/README, including PyPI-downloaded wheels."""
    for directory in PROJECTS:
        project_root = root / directory
        project = tomllib.loads((project_root / "pyproject.toml").read_text())[
            "project"
        ]
        stem, version = project["name"].replace("-", "_"), project["version"]
        readme = (project_root / project["readme"]).read_bytes()
        for suffix in ("-py3-none-any.whl", ".tar.gz"):
            path = dist / (stem + "-" + version + suffix)
            if suffix.endswith(".whl"):
                with zipfile.ZipFile(path) as archive:
                    raw = archive.read(f"{stem}-{version}.dist-info/METADATA")
            else:
                with tarfile.open(path) as archive:
                    member = archive.extractfile(f"{stem}-{version}/PKG-INFO")
                    if member is None:
                        raise ValueError("Missing sdist metadata")
                    raw = member.read()
            metadata = BytesParser().parsebytes(raw)
            description = raw.split(b"\n\n", 1)[1]
            if description != readme:
                raise ValueError(f"Frozen README differs from source: {path.name}")
            expected = {f"{key}, {value}" for key, value in project["urls"].items()}
            if (
                metadata["Name"] != project["name"]
                or metadata["Version"] != version
                or set(metadata.get_all("Project-URL", [])) != expected
            ):
                raise ValueError(
                    f"Frozen package metadata differs from source: {path.name}"
                )


def verify_candidate(root, candidate, dist):
    """Bind final tagged text to the original CI snapshot and eight archives."""
    root, candidate = root.resolve(), candidate.resolve()
    manifest = json.loads((candidate / "candidate.json").read_text())
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=10
    ).strip()
    report = check(root, release=True)
    if (
        manifest.get("schema") != "apizr.release-candidate/v1"
        or manifest.get("repository") != "Alien6-Studio/outerspace-apizr"
        or manifest.get("commit") != commit
        or manifest.get("version") != report["version"]
    ):
        raise ValueError("Release metadata candidate source/version mismatch")
    item = manifest.get("release_metadata", {})
    snapshot = candidate / "release-metadata.json"
    if (
        item.get("file") != snapshot.name
        or snapshot.is_symlink()
        or not snapshot.is_file()
        or snapshot.stat().st_size != item.get("bytes")
        or sha(snapshot.read_bytes()) != item.get("sha256")
    ):
        raise ValueError("Missing or changed pre-build release metadata snapshot")
    verify_snapshot(root, json.loads(snapshot.read_text()), release=True)
    expected = {
        "dist/"
        + tomllib.loads((root / directory / "pyproject.toml").read_text())["project"][
            "name"
        ].replace("-", "_")
        + "-"
        + report["version"]
        + suffix
        for directory in PROJECTS
        for suffix in ("-py3-none-any.whl", ".tar.gz")
    }
    artifacts = manifest.get("artifacts", [])
    if len(artifacts) != 8 or {item["file"] for item in artifacts} != expected:
        raise ValueError("Expected eight qualified metadata archives")
    if {p.name for p in dist.iterdir()} != {Path(n).name for n in expected}:
        raise ValueError("Unexpected release metadata archives")
    for item in artifacts:
        path = dist / Path(item["file"]).name
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != item["bytes"]
            or sha(path.read_bytes()) != item["sha256"]
        ):
            raise ValueError("Release archive differs from qualified candidate")
    verify_archives(root, dist)
    return {**report, "candidate_commit": commit, "qualified_archives": 8}


def verify_public(root, candidate, dist):
    """Download public bytes and prove the already-checked tagged README equality."""
    from scripts.qualification.packaging.prepare_publication import (
        matches,
        public_files,
    )

    report = verify_candidate(root, candidate, dist)
    for directory in PROJECTS:
        project = tomllib.loads((root / directory / "pyproject.toml").read_text())[
            "project"
        ]
        public = public_files(project["name"], report["version"])
        prefix = project["name"].replace("-", "_") + "-" + report["version"]
        expected = {prefix + suffix for suffix in ("-py3-none-any.whl", ".tar.gz")}
        if set(public) != expected:
            raise ValueError(
                "Public release metadata archives are missing or unexpected"
            )
        for name in expected:
            if not matches(dist / name, public[name]):
                raise ValueError(
                    "Public archive differs from the tagged README/metadata"
                )
    return {**report, "public_archive_bytes_equal": True}


def render(root, output):
    """Produce retained previews with the existing documentation renderer."""
    import markdown

    output.mkdir(parents=True, exist_ok=False)
    for directory in PROJECTS:
        project = tomllib.loads((root / directory / "pyproject.toml").read_text())[
            "project"
        ]
        text = (root / directory / project["readme"]).read_text()
        body = markdown.markdown(text, extensions=["fenced_code", "tables"])
        (output / (project["name"] + ".html")).write_text(
            '<!doctype html><meta charset="utf-8"><title>'
            + html.escape(project["name"])
            + '</title><main style="max-width:65rem;margin:3rem auto;font:16px/1.6 system-ui">'
            + body
            + "</main>\n"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument(
        "--release",
        action="store_true",
        help="Refuse every development marker, including on a tag",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Verify the exact retained pre-build source snapshot",
    )
    parser.add_argument(
        "--dist", type=Path, help="Compare frozen archive README/metadata to source"
    )
    parser.add_argument(
        "--candidate", type=Path, help="Original CI candidate inventory and snapshot"
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Read-only download/comparison after publication",
    )
    parser.add_argument(
        "--render",
        type=Path,
        help="Render the four README previews using the docs environment",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.candidate and (not args.dist or args.snapshot):
        parser.error("--candidate requires --dist and replaces --snapshot")
    if args.public and not args.candidate:
        parser.error("--public requires --candidate and --dist")
    report = check(args.source_root, release=args.release)
    if args.candidate:
        verify = verify_public if args.public else verify_candidate
        report = verify(args.source_root, args.candidate, args.dist)
    if args.snapshot:
        verify_snapshot(
            args.source_root,
            json.loads(args.snapshot.read_text()),
            release=args.release,
        )
    if args.dist and not args.candidate:
        verify_archives(args.source_root, args.dist)
    if args.render:
        render(args.source_root, args.render)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

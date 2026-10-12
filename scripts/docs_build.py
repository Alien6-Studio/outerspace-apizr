"""MkDocs hook: identify source, then fingerprint the actual deployed content."""

import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Single declared release state for every public surface. Flip status to
# "stable" (and stable_release to target_version) in the same change that
# rewrites candidate wording; tests/ci/test_release_consistency.py holds the
# README, plugin READMEs, forge defaults, navigation, SECURITY.md and the
# install recording to this declaration.
RELEASE_STATE = {
    "status": "stable",
    "target_version": "0.4.5",
    "stable_release": "0.4.5",
}
CRITICAL = {
    "start/index.html": "Choose your first result",
    "examples/index.html": "Choose an executable example",
    "examples/compare-fraud/index.html": "Compare two fraud experiments",
    "examples/share-prediction/index.html": "Share a prediction from a reviewed Run",
    "examples/business-quote/index.html": "Share an existing business quote",
    "examples/logistics-tool/index.html": "Give a client a delivery-route calculation",
    "examples/research-serving/index.html": "Reuse a function from unfinished research",
    "examples/verified-delivery/index.html": "Hand over a verifiable service image",
    "user-guide/index.html": "Work with your Python code",
    "developer-guide/index.html": "Build with Apizr",
    "developer-guide/compiler/index.html": "Compile a business project from Python",
    "operations-guide/index.html": "Operate generated services",
    "operations-guide/delivery/index.html": "Build and deliver a service image",
    "getting-started/install/index.html": "Install Apizr",
    "getting-started/quickstart-0.4/index.html": "The walkthrough is now at",
    "contributing/publish-0.4/index.html": "Release attachment inventory",
    "releases/0.4.0/index.html": "Core and all three plugins published as 0.4.0rc1.",
    "releases/0.4.1/index.html": "0.4.1 is published and verified.",
    "architecture/delivery-identities/index.html": "DeliveryManifest",
    "reference/delivery-admission/index.html": "admission",
    "reference/multi-destination-delivery/index.html": "resume",
    "reference/operator-policy/index.html": "receipt.sign",
    "getting-started/quickstart/index.html": "Make your first MCP and REST calls",
    "reference/project-plugin-locks/index.html": "Project plugin declarations and locks",
    "reference/apizr-mcp-server/index.html": "Apizr as a local MCP server",
    "index.html": "Apizr 0.4.5",
    "getting-started/data-science/index.html": "From a notebook to a prediction service",
    "releases/0.4.5/index.html": "GitHub and PyPI publication is verified.",
    "releases/0.4.4/index.html": "0.4.4 is published and verified.",
    "releases/0.4.3/index.html": "0.4.3 is published and verified.",
    "releases/0.4.2/index.html": "0.4.2 is published and verified.",
    "getting-started/user-guide/ci-integrations/index.html": "apizr ci",
    "getting-started/onboarding/index.html": "Initialize and check a local project",
    "development/0.4/index.html": "Build and qualify Apizr from source",
    "reference/git-sources/index.html": "One explicit revision",
    "reference/git-ssh/index.html": "ssh-known-hosts",
    "reference/oci-service-plugin/index.html": "Publish a verified service image",
    "reference/attest-delivery-plugin/index.html": "build not supervised by Attest",
    "reference/attest-oci-artifacts/index.html": "remote_state_unconfirmed",
}
ASSETS = (
    "assets/images/logo.png",
    "assets/images/illustration.png",
    "assets/videos/paris-route.jpg",
    "assets/stylesheets/branding.css",
    "assets/javascripts/video.js",
    "downloads/fraud-detection.zip",
    "downloads/business-quote.zip",
    "downloads/logistics-tool.zip",
    "downloads/research-serving.zip",
    "downloads/extension-probe.zip",
    "downloads/verified-delivery.zip",
)

# Downloads are built from reviewed example files, not historical release tags.
EXAMPLES = {
    "fraud-detection": "examples/data-science/fraud-detection",
    "business-quote": "examples/repository-shop/quote-service",
    "logistics-tool": "examples/logistics-tool",
    "research-serving": "examples/research-serving",
    "extension-probe": "examples/extension-probe",
}


def example_archive(name, directory):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ROOT / directory).rglob("*")):
            if (
                not path.is_file()
                or path.name.startswith(".")
                or "__pycache__" in path.parts
            ):
                continue
            entry = zipfile.ZipInfo(
                f"{name}/{path.relative_to(ROOT / directory).as_posix()}"
            )
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, path.read_bytes())
    return data.getvalue()


def on_files(files, config):
    from mkdocs.structure.files import File

    for name, directory in EXAMPLES.items():
        files.append(
            File.generated(
                config,
                f"downloads/{name}.zip",
                content=example_archive(name, directory),
            )
        )
    files.append(
        File.generated(
            config, "downloads/verified-delivery.zip", content=delivery_archive()
        )
    )
    return files


def delivery_archive():
    """Ship fixture tools and data only; product packages come from public PyPI."""
    data = io.BytesIO()
    paths = [
        ROOT / "examples/site-delivery/run.py",
        ROOT / "docs/reference/git-sources.md",
        *sorted((ROOT / "scripts").glob("*.py")),
    ]
    for directory in (
        "examples/repository-shop/quote-service",
        "examples/application-inputs",
        "examples/project-config",
        "examples/governance",
    ):
        paths.extend(
            p
            for p in sorted((ROOT / directory).rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts
        )
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            relative = (
                "run.py" if path.name == "run.py" else path.relative_to(ROOT).as_posix()
            )
            entry = zipfile.ZipInfo("verified-delivery/" + relative)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, path.read_bytes())
    return data.getvalue()


def on_config(config):
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, timeout=10
        ).strip()
    )
    config.extra["docs_build"] = {
        "schema": "apizr.docs-build/v1",
        "source_commit": commit,
        "source_dirty": dirty,
        **RELEASE_STATE,
    }
    return config


def on_post_build(config):
    site = Path(config.site_dir)
    hashes = {}
    for name, content in CRITICAL.items():
        data = (site / name).read_bytes()
        if content not in data.decode():
            raise ValueError(f"Missing documentation content: {name}: {content}")
        hashes[name] = hashlib.sha256(data).hexdigest()
    for name in ASSETS:
        hashes[name] = hashlib.sha256((site / name).read_bytes()).hexdigest()
    # Fingerprint all rendered pages as well as the declared acceptance surfaces.
    for path in sorted(site.rglob("*.html")):
        hashes[path.relative_to(site).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    marker = {**config.extra["docs_build"], "files": hashes}
    (site / "build-info.json").write_text(json.dumps(marker, indent=2) + "\n")

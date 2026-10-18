"""MkDocs hook: identify source, then fingerprint the actual deployed content."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from academy_recordings import lesson_markdown, recordings  # noqa: E402

RELEASE_STATE = json.loads((ROOT / "site.json").read_text())
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
    "architecture/index.html": "Understand Apizr's architecture",
    "architecture/overview/index.html": "Capability Compiler architecture",
    "architecture/system-boundaries/index.html": "Components and responsibilities",
    "architecture/compilation-flow/index.html": "From source to interfaces",
    "architecture/experiments-and-artifacts/index.html": "Experiments and artifact identities",
    "architecture/execution-boundaries/index.html": "Request and execution boundaries",
    "architecture/extensions-and-delivery/index.html": "Extensions and service delivery",
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
    "index.html": "Apizr 0.4.6",
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
    "academy/index.html": "Apizr Academy",
    "academy/capabilities/index.html": "What is a capability?",
    "academy/readiness/index.html": "What does Readiness decide?",
    "academy/exposure/index.html": "What does Exposure select?",
    "academy/execution/index.html": "Where does execution happen?",
    "academy/interfaces/index.html": "What do REST and MCP expose?",
    "architecture/transport-admission/index.html": "REST and MCP admission budgets",
    "releases/0.4.6/index.html": "Apizr 0.4.6",
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
    "assets/videos/tutorial-install.jpg",
    "assets/videos/tutorial-inspect.jpg",
    "assets/videos/tutorial-rest.jpg",
    "assets/videos/tutorial-mcp.jpg",
    "assets/videos/tutorial-oci.jpg",
    "assets/javascripts/feedback.js",
)


def on_config(config):
    recordings(ROOT)
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, timeout=10
        ).strip()
    )
    config.extra["docs_build"] = {
        "schema": "apizr.website-build/v1",
        "source_branch": "gh-pages",
        "source_commit": commit,
        "source_dirty": dirty,
        **{k: v for k, v in RELEASE_STATE.items() if k != "schema"},
    }
    return config


def on_page_markdown(markdown, page, config, files):
    return lesson_markdown(markdown, page, recordings(ROOT))


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
    for path in sorted(site.rglob("*")):
        if path.is_symlink():
            raise ValueError("Website output contains a symlink")
        if path.is_file() and path.name != "build-info.json":
            hashes[path.relative_to(site).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    marker = {**config.extra["docs_build"], "files": hashes}
    (site / "build-info.json").write_text(json.dumps(marker, indent=2) + "\n")

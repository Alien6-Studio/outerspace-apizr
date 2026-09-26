"""MkDocs hook: identify source, then fingerprint the actual deployed content."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRITICAL = {
    "reference/project-plugin-locks/index.html": "Project plugin declarations and locks",
    "reference/apizr-mcp-server/index.html": "Apizr as a local MCP server",
    "index.html": "Preparing 0.4",
    "development/0.4/index.html": "Not released",
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
)


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
        "status": "development",
        "target_version": "0.4.0",
        "stable_release": "0.3.0",
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
    marker = {**config.extra["docs_build"], "files": hashes}
    (site / "build-info.json").write_text(json.dumps(marker, indent=2) + "\n")

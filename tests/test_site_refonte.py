"""Reader paths retain published links/media and ship standalone fixture inputs."""

import hashlib
import io
import json
import re
import runpy
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BUILD = runpy.run_path(str(ROOT / "scripts/docs_build.py"))
INVENTORY = json.loads((ROOT / "review/site-refonte/page-migration.json").read_text())


def test_every_original_public_page_has_a_review_decision():
    baseline = INVENTORY["baseline_commit"]
    assert re.fullmatch("[0-9a-f]{40}", baseline)
    rows = INVENTORY["pages"]
    # The retained baseline also works in a shallow CI checkout.
    assert len(rows) == INVENTORY["baseline_page_count"] == 104
    assert len({row["source"] for row in rows}) == 104
    assert sum(len(row["anchors"]) for row in rows) == 759
    assert all((ROOT / "docs" / row["source"]).is_file() for row in rows)
    assert all(
        row["decision"] and row["destination"] and row["validation"] for row in rows
    )


def test_six_primary_paths_and_native_consent_aware_git_widget():
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text())
    assert [next(iter(entry)) for entry in config["nav"]] == [
        "Start here",
        "Examples",
        "User guide",
        "Developer guide",
        "Operations guide",
        "Reference",
    ]
    assert config["extra"]["consent"]["cookies"]["github"]["checked"] is False
    assert config["extra"]["consent"]["cookies"]["analytics"]["checked"] is False
    source = (ROOT / "overrides/partials/source.html").read_text()
    assert 'data-md-component="source"' in source
    assert "Docs " not in source


def test_existing_video_ids_transcript_and_hero_bytes_are_preserved():
    for row in INVENTORY["pages"]:
        name = "docs/" + row["source"]
        current = (ROOT / name).read_text()
        assert set(row["video_ids"]) <= set(
            re.findall(r'data-apizr-video="([^"]+)"', current)
        ), name
        if row["source"] == "index.md":
            transcript = re.search(
                r'<div class="apizr-demo-transcript__body">(.*?)</div>', current, re.S
            )
            assert transcript
            assert (
                hashlib.sha256(transcript.group(1).encode()).hexdigest()
                == INVENTORY["home_transcript_sha256"]
            )
    for name, expected in INVENTORY["preserved_asset_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected


def test_downloads_are_reproducible_and_fixture_contains_no_product_source():
    for name, directory in BUILD["EXAMPLES"].items():
        first = BUILD["example_archive"](name, directory)
        assert first == BUILD["example_archive"](name, directory)
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            assert archive.namelist()
            assert not any(
                "__pycache__" in p or p.endswith(".pyc") for p in archive.namelist()
            )
    fixture = BUILD["delivery_archive"]()
    assert fixture == BUILD["delivery_archive"]()
    with zipfile.ZipFile(io.BytesIO(fixture)) as archive:
        names = archive.namelist()
        assert "verified-delivery/run.py" in names
        assert "verified-delivery/docs/reference/git-sources.md" in names
        assert (
            "verified-delivery/examples/repository-shop/quote-service/src/api.py"
            in names
        )
        assert not any(
            "/src/apizr/" in p or p.endswith((".key", ".pem")) for p in names
        )


@pytest.mark.parametrize("key", ["APIZR_RELEASE_SET", "APIZR_RELEASE_TARGET"])
def test_public_fixture_refuses_candidate_inputs_before_download(
    monkeypatch, tmp_path, key
):
    package = runpy.run_path(str(ROOT / "scripts/site_example_packages.py"))
    monkeypatch.setenv("APIZR_DOCS_PUBLIC_PROOF", "1")
    monkeypatch.setenv(key, str(tmp_path))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: pytest.fail("must refuse before external effects"),
    )
    with pytest.raises(ValueError, match="cannot consume candidate"):
        package["copy_public_closure"]("oci", tmp_path / "untouched")
    assert not (tmp_path / "untouched").exists()

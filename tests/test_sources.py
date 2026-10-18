import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = json.loads((ROOT / "tests/fixtures/page-migration.json").read_text())


def test_historical_pages_videos_and_artwork_are_preserved():
    for row in INVENTORY["pages"]:
        page = ROOT / "docs" / row["source"]
        assert page.is_file(), row["source"]
        assert set(row["video_ids"]) <= set(
            re.findall(r'data-apizr-video="([^"]+)"', page.read_text())
        )
    for name, expected in INVENTORY["preserved_asset_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected


def test_downloads_have_an_immutable_product_source_and_verified_bytes():
    info = json.loads((ROOT / "downloads.json").read_text())
    config = json.loads((ROOT / "site.json").read_text())
    assert re.fullmatch("[0-9a-f]{40}", info["product_source_commit"])
    assert info["product_source_commit"] == config["product_source_commit"]
    assert len(info["sha256"]) == 7
    for name, expected in info["sha256"].items():
        archive = ROOT / "docs/downloads" / name
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
        with zipfile.ZipFile(archive) as data:
            assert data.testzip() is None
            assert data.namelist()
            assert not any(
                n.startswith("/") or ".." in Path(n).parts or "/src/apizr/" in n
                for n in data.namelist()
            )


def test_academy_contains_all_published_lessons_without_preloading_youtube():
    source = (ROOT / "docs/academy/index.md").read_text()
    assert len(re.findall("data-apizr-video=", source)) == 13
    assert 'data-apizr-video="zkujF-thyyQ"' in source
    assert "<iframe" not in source
    script = (ROOT / "docs/assets/javascripts/video.js").read_text()
    assert "youtube-nocookie.com" in script


def test_pages_workflow_has_no_product_checkout_or_branch_push():
    import yaml

    workflow = yaml.load(
        (ROOT / ".github/workflows/site.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert workflow["on"]["push"]["branches"] == ["gh-pages"]
    deploy = workflow["jobs"]["deploy"]
    assert workflow["permissions"] == {"contents": "read"}
    assert deploy["needs"] == "quality"
    assert deploy["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert "refs/heads/gh-pages" in deploy["if"]
    content = json.dumps(workflow)
    assert "git push" not in content and "ghp_import" not in content
    assert "uv build" not in content and "outerspace-apizr==" not in content


def test_academy_preparation_uses_only_the_frozen_site_materials(tmp_path):
    import subprocess
    import sys

    destination = tmp_path / "lessons"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "academy/academy_lessons.py"),
            "--output",
            str(destination),
        ],
        cwd=tmp_path,
        check=True,
    )
    manifest = json.loads((destination / "manifest.json").read_text())
    assert len(manifest["lessons"]) == 7
    assert (
        manifest["product_source_commit"]
        == json.loads((ROOT / "site.json").read_text())["product_source_commit"]
    )
    assert (destination / "xii-vscode/materials/wine_experiments.py").is_file()
    assert (destination / "xi-jupyter/materials/fraud-thresholds.ipynb").is_file()

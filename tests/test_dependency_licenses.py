"""Prove that changes cannot inherit a prior license review by accident."""

import copy
import json
import runpy
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = runpy.run_path(str(ROOT / "scripts/check_dependency_licenses.py"))


@pytest.fixture
def inputs():
    return [
        tomllib.loads((ROOT / "uv.lock").read_text()),
        *(
            json.loads((ROOT / "policy" / name).read_text())
            for name in (
                "dependency-licenses.json",
                "dependency-policy.json",
                "dependency-license-texts.json",
            )
        ),
    ]


def test_current_universal_graph_has_preserved_license_evidence(inputs):
    report = CHECKER["validate_inventory"](*inputs)
    assert report["packages"] == sum(
        "registry" in p["source"] for p in inputs[0]["package"]
    )
    assert report["result"] == "pass"
    assert report["limitations"]


@pytest.mark.parametrize(
    ("expression", "allowed", "expected"),
    [
        ("MIT OR GPL-2.0-only", {"MIT"}, True),
        ("MIT AND GPL-2.0-only", {"MIT"}, False),
        ("MIT OR Apache-2.0 AND GPL-2.0-only", {"MIT"}, True),
        ("(MIT OR Apache-2.0) AND GPL-2.0-only", {"MIT"}, False),
        ("MIT AND (Apache-2.0 OR BSD-3-Clause)", {"MIT", "BSD-3-Clause"}, True),
        ("Apache-2.0 WITH LLVM-exception", {"Apache-2.0"}, False),
        ("Apache-2.0 WITH LLVM-exception", {"Apache-2.0 WITH LLVM-exception"}, True),
        ("LicenseRef-Unreviewed", {"MIT"}, False),
    ],
)
def test_license_choices_do_not_drop_cumulative_obligations(
    expression, allowed, expected
):
    assert CHECKER["license_allowed"](expression, allowed) is expected


@pytest.mark.parametrize(
    "expression",
    ["", "Unknown-License", "MIT AND", "MIT OR", "MIT; True", "MIT OR (BSD-3-Clause"],
)
def test_invalid_expressions_fail_closed(expression):
    with pytest.raises(ValueError):
        CHECKER["license_allowed"](expression, {"MIT"})


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "stale",
        "pending",
        "no-notes",
        "new-version",
        "archive-hash",
        "archive-url",
        "evidence-archive",
        "missing-text",
        "altered-text",
        "missing-expression",
        "unapproved-license",
        "unknown-license",
        "unscoped-component",
        "component-evidence",
        "exception-version",
        "exception-reason",
        "exception-evidence",
        "denied-name",
        "direct-source",
        "extra-text",
    ],
)
def test_inventory_changes_require_review(inputs, change):
    lock, inventory, policy, texts = inputs
    review = inventory["packages"][0]
    package = next(p for p in lock["package"] if p["name"] == review["name"])
    if change == "missing":
        inventory["packages"].pop()
    elif change == "duplicate":
        inventory["packages"].append(copy.deepcopy(review))
    elif change == "stale":
        inventory["packages"].append({**review, "name": "removed-package"})
    elif change == "pending":
        review["status"] = "pending"
    elif change == "no-notes":
        review["notes"] = ""
    elif change == "new-version":
        package["version"] = "999.0"
    elif change == "archive-hash":
        package["wheels"][0]["hash"] = "sha256:" + "0" * 64
    elif change == "archive-url":
        package["wheels"][0]["url"] += "?replacement"
    elif change == "evidence-archive":
        review["evidence_archive"]["hash"] = "sha256:" + "0" * 64
    elif change == "missing-text":
        del texts["texts"][review["license_files"][0]["sha256"]]
    elif change == "altered-text":
        texts["texts"][review["license_files"][0]["sha256"]] += "altered"
    elif change == "missing-expression":
        review["components"] = []
    elif change == "unapproved-license":
        review["components"][0]["expression"] = "MIT AND GPL-2.0-only"
    elif change == "unknown-license":
        review["components"][0]["expression"] = "Unknown-License"
    elif change == "unscoped-component":
        review["components"][0]["scope"] = ""
    elif change == "component-evidence":
        review["components"][0]["evidence_sha256"] = ["0" * 64]
    elif change == "exception-version":
        policy["exceptions"][0]["version"] = "999.0"
    elif change == "exception-reason":
        policy["exceptions"][0]["reason"] = ""
    elif change == "exception-evidence":
        policy["exceptions"][0]["evidence_sha256"] = ["0" * 64]
    elif change == "denied-name":
        # PEP 503 spelling variants must not evade the denylist.
        policy["denied_packages"].append(
            {"name": review["name"].upper().replace("-", "_"), "reason": "Test denial"}
        )
    elif change == "direct-source":
        package["source"] = {"url": "https://example.com/package.tar.gz"}
    elif change == "extra-text":
        texts["texts"]["0" * 64] = "Unreferenced"
    with pytest.raises(ValueError):
        CHECKER["validate_inventory"](*inputs)


def test_collector_checks_archive_hash_and_reads_without_extraction(
    tmp_path, monkeypatch
):
    import hashlib
    import io
    import tarfile

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    collect = runpy.run_path(str(ROOT / "scripts/collect_dependency_licenses.py"))[
        "notices"
    ]
    buffer = io.BytesIO()
    text = b"Preserve this notice.\r\n"
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        notice = tarfile.TarInfo("../LICENSE")
        notice.size = len(text)
        archive.addfile(notice, io.BytesIO(text))
        link = tarfile.TarInfo("other/LICENSE")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        archive.addfile(link)
        code = tarfile.TarInfo("setup.py")
        raw = b"raise RuntimeError('must never execute')"
        code.size = len(raw)
        archive.addfile(code, io.BytesIO(raw))
    data = buffer.getvalue()
    monkeypatch.chdir(tmp_path)
    result = collect(data, {"hash": "sha256:" + hashlib.sha256(data).hexdigest()})
    assert result == [
        {
            "path": "../LICENSE",
            "sha256": hashlib.sha256(text).hexdigest(),
            "text": text.decode(),
        }
    ]
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError, match="SHA-256"):
        collect(
            data + b"tamper", {"hash": "sha256:" + hashlib.sha256(data).hexdigest()}
        )


def test_collector_preserves_nonstandard_license_names_in_wheels(monkeypatch):
    import hashlib
    import io
    import zipfile

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    collect = runpy.run_path(str(ROOT / "scripts/collect_dependency_licenses.py"))[
        "notices"
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("dist-info/licenses/mit.LICENSE", "MIT evidence\n")
        archive.writestr("data/index.ABOUT", "Attribution\n")
    data = buffer.getvalue()
    result = collect(data, {"hash": "sha256:" + hashlib.sha256(data).hexdigest()})
    assert {r["path"] for r in result} == {
        "dist-info/licenses/mit.LICENSE",
        "data/index.ABOUT",
    }

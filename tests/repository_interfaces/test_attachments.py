"""Optional opaque evidence stays bound without changing ordinary manifests."""

import pytest

from apizr.capabilities.model import Digest
from apizr.repository.serialization import canonical_bytes
from apizr.repository_interfaces.evidence import attach_evidence
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.model import RestManifest


@pytest.mark.parametrize(
    "name,content",
    [
        ("../evidence.json", b"{}\n"),
        ("data.txt", b"{}\n"),
        (".hidden.json", b"{}\n"),
        ("repository-interface.json", b"{}\n"),
        ("evidence.json", b" " * (1024 * 1024 + 1)),
        ("evidence.json", b"[]\n"),
        ("evidence.json", b'{"a":1, "b":2}\n'),
        ("evidence.json", b'{"a":1,"a":2}\n'),
    ],
)
def test_attachment_must_be_new_bounded_canonical_json(inputs, name, content):
    bundle = render_repository_bundle(*inputs, interface="rest")
    with pytest.raises(ValueError):
        attach_evidence(bundle, interface="rest", name=name, content=content)


@pytest.mark.parametrize("fault", ["missing", "extra", "digest"])
def test_attachment_cannot_legitimize_tampered_bundle(inputs, fault):
    bundle = render_repository_bundle(*inputs, interface="rest")
    if fault == "missing":
        del bundle["source/shop/api.py"]
    elif fault == "extra":
        bundle["extra.py"] = b"raise RuntimeError()"
    else:
        bundle["source/shop/api.py"] += b" "
    with pytest.raises(ValueError, match="disagree"):
        attach_evidence(bundle, interface="rest", name="evidence.json", content=b"{}\n")


def test_only_attachment_and_manifest_bytes_change(inputs):
    bundle = render_repository_bundle(*inputs, interface="rest")
    before = dict(bundle)
    attached = attach_evidence(
        bundle, interface="rest", name="evidence.json", content=b"{}\n"
    )
    assert before == bundle
    assert {
        n: data
        for n, data in attached.items()
        if n not in {"evidence.json", "apizr-repository-rest.json"}
    } == {n: data for n, data in before.items() if n != "apizr-repository-rest.json"}
    manifest = RestManifest.model_validate_json(attached["apizr-repository-rest.json"])
    assert manifest.artifacts.pop("evidence.json") == Digest.of_bytes(b"{}\n")
    assert canonical_bytes(manifest) == before["apizr-repository-rest.json"]

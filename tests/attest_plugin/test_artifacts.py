"""Admission/state tests; real ORAS/registry interoperability runs separately."""

import copy
import json

import pytest
from apizr_attest import artifacts as a
from apizr_attest.delivery import FILES, canonical
from apizr_attest.model import (
    AttestError,
    DeliveryResult,
    DiscoverRequest,
    FetchRequest,
    PublishRequest,
)
from apizr_oci.model import BuildError
from apizr_oci.oras import OCI_MANIFEST, sha

IMAGE = "registry.test:5443/services/rest@sha256:" + "a" * 64
SUBJECT = {"mediaType": OCI_MANIFEST, "digest": IMAGE.split("@")[1], "size": 123}


def manifest(files):
    return {
        "schemaVersion": 2,
        "mediaType": OCI_MANIFEST,
        "artifactType": a.ARTIFACT_TYPE,
        "config": a.EMPTY,
        "annotations": a.ANNOTATIONS,
        "subject": SUBJECT,
        "layers": [
            {
                "mediaType": a.LAYER_TYPE,
                "digest": sha(files[n]),
                "size": len(files[n]),
                "annotations": {"org.opencontainers.image.title": n},
            }
            for n in sorted(FILES)
        ],
    }


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    proof = tmp_path / "source"
    proof.mkdir()
    files = {n: ("public " + n).encode() for n in FILES}
    for n, raw in files.items():
        p = proof / n
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(raw)
    (proof / "secret").write_text("not exported")
    transport = {
        "tool": {
            "executable": "/explicit/oras",
            "version": "1.3.4",
            "sha256": "0" * 64,
        },
        "authentication": {"config_file": "/explicit/auth"},
    }
    common = {
        "expected_reference": IMAGE,
        "expected_signer": "b" * 64,
        "trust_store": str(tmp_path / "trust"),
        "tool": {
            "executable": "/explicit/attest",
            "version": "0.1.0",
            "sha256": "0" * 64,
        },
        "transport": transport,
    }
    publish = PublishRequest.model_validate(
        common | {"schema": "apizr.publish-proof/v1", "proof_dir": str(proof)}
    )
    verified = DeliveryResult(
        reference=IMAGE,
        manifest_digest=SUBJECT["digest"],
        signer="b" * 64,
        receipt_sha256=sha(files["receipt.yaml"])[7:],
        checks=dict.fromkeys(
            ("schema", "consistency", "signature", "timestamp", "recompute"), "pass"
        ),
    )
    monkeypatch.setattr(a, "check_proof", lambda *args: verified)
    state = {
        "uploaded": False,
        "fault": None,
        "files": files,
        "manifest": manifest(files),
        "calls": [],
    }

    class Registry:
        repository = IMAGE.split("@")[0]

        def manifest(self, reference):
            if reference == IMAGE:
                return b"image", SUBJECT
            raw = canonical(state["manifest"])
            return raw, {
                "mediaType": OCI_MANIFEST,
                "size": len(raw),
                "digest": sha(raw),
            }

        def discover(self, *args):
            if state["fault"] == "unsupported":
                raise BuildError("referrers_api_unavailable")
            if state["fault"] == "confirmation" and state["uploaded"]:
                raise BuildError("network")
            return (
                []
                if not state["uploaded"]
                else [
                    {
                        "reference": self.repository
                        + "@"
                        + sha(canonical(state["manifest"]))
                    }
                ]
            )

        def call(self, args, **kwargs):
            state["uploaded"] = True
            state["calls"].append(args)
            assert "--distribution-spec" in args and "v1.1-referrers-api" in args
            snapshot = kwargs["cwd"]
            assert {
                str(p.relative_to(snapshot)) for p in snapshot.rglob("*") if p.is_file()
            } == set(FILES)
            # Change original files after verification: only snapshot bytes transfer.
            (proof / "receipt.yaml").write_text("changed after validation")
            assert (snapshot / "receipt.yaml").read_bytes() == files["receipt.yaml"]
            raw = canonical(state["manifest"])
            return canonical(
                {
                    "reference": self.repository + "@" + sha(raw),
                    "mediaType": OCI_MANIFEST,
                    "digest": sha(raw),
                    "size": len(raw),
                    "artifactType": a.ARTIFACT_TYPE,
                }
            )

        def blob(self, desc):
            if state["fault"] == "blob":
                raise BuildError("blob_integrity_failed")
            return next(raw for raw in files.values() if sha(raw) == desc["digest"])

    monkeypatch.setattr(a, "registry", lambda *args: Registry())
    return publish, common, state, files


def test_publish_fetch_exact_bytes_and_identities(fixture, tmp_path):
    request, common, state, files = fixture
    work = tmp_path / "publisher"
    work.mkdir()
    result = a.execute_publish(request, work)
    assert (
        result.receipt_published
        and result.receipt_sha256 == sha(files["receipt.yaml"])[7:]
    )
    fetch = FetchRequest.model_validate(
        common
        | {
            "schema": "apizr.fetch-proof/v1",
            "artifact_reference": result.artifact_reference,
            "output_dir": str(tmp_path / "export"),
        }
    )
    work = tmp_path / "consumer"
    work.mkdir()
    recovered = a.execute_fetch(fetch, work)
    assert recovered.verification == result.verification
    assert {n: (tmp_path / "export" / n).read_bytes() for n in FILES} == files
    with pytest.raises(AttestError, match="exists"):
        a.execute_fetch(fetch, work)


@pytest.mark.parametrize("fault", ["unsupported", "confirmation", "invalid-proof"])
def test_publish_failures_preserve_state(fixture, tmp_path, monkeypatch, fault):
    request, _, state, _ = fixture
    state["fault"] = fault
    if fault == "invalid-proof":
        monkeypatch.setattr(
            a,
            "check_proof",
            lambda *args: (_ for _ in ()).throw(AttestError("invalid")),
        )
    work = tmp_path / "work"
    work.mkdir()
    if fault == "confirmation":
        result = a.execute_publish(request, work)
        assert result.state == "remote_state_unconfirmed"
        assert result.receipt_published is False and result.artifact_reference is None
    else:
        with pytest.raises((AttestError, BuildError), match="invalid|unavailable"):
            a.execute_publish(request, work)
    assert state["uploaded"] == (fault == "confirmation")


@pytest.mark.parametrize(
    "fault",
    [
        "type",
        "subject",
        "config",
        "count",
        "duplicate",
        "path",
        "extra",
        "url",
        "data",
        "size",
        "digest",
        "order",
        "annotations",
    ],
)
def test_hostile_descriptors_before_blob_fetch(fixture, fault):
    _, _, state, _ = fixture
    value = copy.deepcopy(state["manifest"])
    if fault == "type":
        value["artifactType"] = "foreign"
    if fault == "subject":
        value["subject"] = SUBJECT | {"digest": "sha256:" + "b" * 64}
    if fault == "config":
        value["config"] = a.EMPTY | {"urls": ["https://external"]}
    if fault == "count":
        value["layers"].pop()
    if fault == "duplicate":
        value["layers"][1] = value["layers"][0]
    if fault == "path":
        value["layers"][0]["annotations"]["org.opencontainers.image.title"] = (
            "../../secret"
        )
    if fault == "extra":
        value["layers"][0]["annotations"]["org.opencontainers.image.title"] = "key.pem"
    if fault == "url":
        value["layers"][0]["urls"] = ["https://external"]
    if fault == "data":
        value["layers"][0]["data"] = "e30="
    if fault == "size":
        value["layers"][0]["size"] = 1048577
    if fault == "digest":
        value["layers"][0]["digest"] = "sha256:bad"
    if fault == "order":
        value["layers"].reverse()
    if fault == "annotations":
        value["annotations"]["date"] = "today"
    with pytest.raises((AttestError, BuildError)):
        a.manifest_files(canonical(value), SUBJECT)


def test_fetch_no_export_on_invalid_receipt(fixture, tmp_path, monkeypatch):
    _, common, state, _ = fixture
    raw = canonical(state["manifest"])
    request = FetchRequest.model_validate(
        common
        | {
            "schema": "apizr.fetch-proof/v1",
            "artifact_reference": IMAGE.split("@")[0] + "@" + sha(raw),
            "output_dir": str(tmp_path / "export"),
        }
    )
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(
        a,
        "check_proof",
        lambda *args: (_ for _ in ()).throw(AttestError("bad signature")),
    )
    with pytest.raises(AttestError):
        a.execute_fetch(request, work)
    assert not (tmp_path / "export").exists()
    cross = request.model_copy(
        update={
            "artifact_reference": request.artifact_reference.replace(
                "/services/", "/foreign/"
            )
        }
    )
    with pytest.raises(AttestError, match="cross_repository"):
        a.execute_fetch(cross, work)


def test_discover_is_untrusted_and_no_attest_inputs(fixture, tmp_path, monkeypatch):
    _, common, state, _ = fixture
    request = DiscoverRequest.model_validate(
        {
            "schema": "apizr.discover-proofs/v1",
            "expected_reference": IMAGE,
            "transport": common["transport"],
        }
    )
    assert a.execute_discover(request, tmp_path).candidates == []
    with pytest.raises(ValueError):
        DiscoverRequest.model_validate(
            request.model_dump(by_alias=True) | {"key_file": "/secret"}
        )


@pytest.mark.parametrize("op", ["publish", "discover", "fetch"])
def test_typed_api_and_protocol(fixture, tmp_path, monkeypatch, capsys, op):
    import io
    import sys
    from types import SimpleNamespace

    from apizr_attest import api, protocol
    from apizr_attest.model import DiscoverResult, FetchResult, PublishResult

    request, common, state, files = fixture
    verification = a.check_proof()
    fields = {
        "image_reference": IMAGE,
        "image_digest": SUBJECT["digest"],
        "artifact_reference": IMAGE,
        "artifact_manifest_digest": SUBJECT["digest"],
        "receipt_sha256": verification.receipt_sha256,
        "verification": verification,
    }
    if op == "publish":
        reply = PublishResult(**fields)
    elif op == "fetch":
        request = FetchRequest.model_validate(
            common
            | {
                "schema": "apizr.fetch-proof/v1",
                "artifact_reference": IMAGE,
                "output_dir": str(tmp_path / "out"),
            }
        )
        reply = FetchResult(**fields)
    else:
        request = DiscoverRequest.model_validate(
            {
                "schema": "apizr.discover-proofs/v1",
                "expected_reference": IMAGE,
                "transport": common["transport"],
            }
        )
        reply = DiscoverResult(image_reference=IMAGE, candidates=[])
    monkeypatch.setattr(
        api,
        "invoke_extension",
        lambda *args, **kwargs: SimpleNamespace(result=reply.model_dump(by_alias=True)),
    )
    assert getattr(api, op)(request) == reply
    monkeypatch.setattr(protocol, "execute_" + op, lambda *args: reply)
    raw = canonical(
        {
            "protocol": "apizr.extension/v1",
            "request_id": "0" * 32,
            "operation": op,
            "arguments": request.model_dump(by_alias=True),
        }
    )
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw)))
    assert (
        protocol.main() == 0 and json.loads(capsys.readouterr().out)["status"] == "ok"
    )


def test_documented_argument_files_validate():
    import re
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2] / "docs/reference/attest-oci-artifacts.md"
    ).read_text()
    documents = re.findall(r"```json\n(.*?)\n```", text, re.S)
    assert len(documents) == 3
    for model, document in zip(
        (PublishRequest, DiscoverRequest, FetchRequest), documents, strict=True
    ):
        model.model_validate_json(document)


@pytest.mark.parametrize(
    "change",
    [
        {"state": "verified", "receipt_published": False},
        {"state": "verified", "artifact_reference": None},
        {"state": "remote_state_unconfirmed"},
        {"state": "remote_state_unconfirmed", "receipt_published": False},
    ],
)
def test_publication_cannot_claim_unverified_identity(fixture, change):
    from apizr_attest.model import PublishResult

    value = {
        "image_reference": IMAGE,
        "image_digest": SUBJECT["digest"],
        "artifact_reference": IMAGE,
        "artifact_manifest_digest": SUBJECT["digest"],
        "receipt_sha256": "a" * 64,
        "verification": a.check_proof(),
    }
    with pytest.raises(ValueError):
        PublishResult.model_validate(value | change)

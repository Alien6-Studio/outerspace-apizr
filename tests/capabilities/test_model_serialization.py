import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from apizr.capabilities import (
    CapabilityDocument,
    canonical_bytes,
    document_digest,
    inspect_file,
    inspect_source,
)
from apizr.capabilities.model import (
    Digest,
    Effect,
    EffectValue,
    Parameter,
    ParameterKind,
    Signature,
    Source,
    SourceSpan,
)
from apizr.capabilities.types import Evidence, Expression

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/capability_ir/v1"


def test_reviewed_golden_and_json_round_trip():
    document = inspect_file(FIXTURE / "basic.py", module_name="pricing")
    expected = (FIXTURE / "basic.json").read_bytes()
    assert document.model_dump(mode="json") == json.loads(expected)
    assert canonical_bytes(
        CapabilityDocument.model_validate_json(expected)
    ) == canonical_bytes(document)
    assert b"\n" not in canonical_bytes(document)[:-1]
    assert canonical_bytes(document).endswith(b"\n")
    assert (
        document_digest(document).value
        == hashlib.sha256(canonical_bytes(document)).hexdigest()
    )


def test_committed_schema_matches_the_model():
    committed = (ROOT / "docs/specs/apizr-capability-v1.schema.json").read_text()
    assert (
        committed
        == json.dumps(CapabilityDocument.model_json_schema(), indent=2, sort_keys=True)
        + "\n"
    )


def test_empty_document_has_exact_canonical_encoding():
    document = inspect_source(b"", module_name="empty")
    assert canonical_bytes(document) == (
        b'{"capabilities":[],"diagnostics":[],"schema_version":"apizr.capability/v1",'
        b'"source":{"digest":{"algorithm":"sha256","value":"'
        + hashlib.sha256(b"").hexdigest().encode()
        + b'"},"kind":"python","module":"empty","transformed_digest":null}}\n'
    )


def test_ordering_is_canonical_even_for_manually_constructed_documents():
    document = inspect_source(
        "def z(): pass\ndef a(): pass\n@wrap\ndef c(): pass\nif False:\n def d(): pass",
        module_name="ordered",
    )
    reordered = CapabilityDocument(
        source=document.source,
        capabilities=tuple(reversed(document.capabilities)),
        diagnostics=tuple(reversed(document.diagnostics)),
    )
    assert [c.name for c in document.capabilities] == ["a", "c", "d", "z"]
    assert canonical_bytes(reordered) == canonical_bytes(document)


@pytest.mark.parametrize(
    "raw",
    [
        b"# coding: latin-1\r\ndef caf\xe9(): pass\r\n",
        b"\xef\xbb\xbfdef f(): pass\n",
        "def café(): pass\n".encode(),
    ],
)
def test_source_digest_hashes_exact_bytes_not_decoded_text(raw, tmp_path):
    path = tmp_path / "different-name.py"
    path.write_bytes(raw)
    document = inspect_file(path, module_name="logical.name")
    assert document.source.digest == Digest.of_bytes(raw)
    assert document.source.digest.value == hashlib.sha256(raw).hexdigest()
    assert canonical_bytes(document) == canonical_bytes(
        inspect_source(raw, module_name="logical.name")
    )
    assert str(tmp_path).encode() not in canonical_bytes(document)


def test_strings_have_utf8_digest_and_unicode_is_not_ascii_escaped():
    source = "def café(): pass"
    document = inspect_source(source, module_name="café")
    assert (
        document.source.digest.value
        == hashlib.sha256(source.encode("utf-8")).hexdigest()
    )
    assert "café".encode() in canonical_bytes(document)
    assert inspect_source("def f(): pass", module_name="K").source.module == "K"


@pytest.mark.parametrize(
    "module",
    ["", "../module", "a/b", "a\\b", "a..b", "a:def", "a.class", "/absolute", "1bad"],
)
def test_invalid_logical_modules_are_rejected(module):
    with pytest.raises(ValueError, match="logical dotted"):
        inspect_source("", module_name=module)


@pytest.mark.parametrize(
    "raw", [b"def :", b"# coding: unknown-encoding\n", b"# coding: utf-8\n\xff"]
)
def test_invalid_input_raises_without_partial_document(raw):
    with pytest.raises((SyntaxError, UnicodeError)):
        inspect_source(raw, module_name="broken")


def test_duplicate_ids_and_inconsistent_modules_are_invalid_documents():
    document = inspect_source("def f(): pass", module_name="valid")
    capability = document.capabilities[0]
    with pytest.raises(ValidationError, match="Duplicate capability IDs"):
        CapabilityDocument(
            source=document.source, capabilities=(capability, capability)
        )
    with pytest.raises(ValidationError, match="Source modules"):
        CapabilityDocument(
            source=Source(kind="python", module="other", digest=document.source.digest),
            capabilities=(capability,),
        )
    with pytest.raises(ValidationError, match="frozen"):
        document.schema_version = "apizr.capability/v1"


@pytest.mark.parametrize(
    "change",
    [
        {"id": "random"},
        {"name": "other"},
        {"qualified_name": "Class.f"},
        {"kind": "method"},
        {"unknown_field": True},
    ],
)
def test_invalid_capability_shapes_are_rejected(change):
    data = inspect_source("def f(): pass", module_name="valid").model_dump(mode="json")
    data["capabilities"][0].update(change)
    with pytest.raises(ValidationError):
        CapabilityDocument.model_validate(data)


def test_overload_locations_must_match_symbol():
    data = inspect_source(
        "from typing import overload\n@overload\ndef f(x: int): ...\ndef f(x): pass",
        module_name="valid",
    ).model_dump(mode="json")
    data["capabilities"][0]["overloads"][0]["source"]["symbol"] = "other"
    with pytest.raises(ValidationError, match="Overload source"):
        CapabilityDocument.model_validate(data)


def test_version_is_explicit_and_not_package_version():
    data = inspect_source("", module_name="valid").model_dump()
    data["schema_version"] = "apizr.capability/v2"
    with pytest.raises(ValidationError):
        CapabilityDocument.model_validate(data)


def test_model_invariants_do_not_accept_contradictory_contracts():
    with pytest.raises(ValidationError, match="End line"):
        SourceSpan(module="a", symbol="f", line=2, end_line=1)
    with pytest.raises(ValidationError):
        Digest(value="ABC")
    digest = Digest.of_bytes(b"")
    with pytest.raises(ValidationError, match="transformed"):
        Source(kind="notebook", module="a", digest=digest)
    with pytest.raises(ValidationError, match="transformed"):
        Source(kind="python", module="a", digest=digest, transformed_digest=digest)
    parameter = Parameter(name="x", kind=ParameterKind.POSITIONAL_ONLY, required=True)
    with pytest.raises(ValidationError, match="Duplicate parameter"):
        Signature(parameters=(parameter, parameter))
    with pytest.raises(ValidationError, match="Required"):
        Parameter(
            name="x",
            kind=ParameterKind.POSITIONAL_ONLY,
            required=True,
            default=Expression(declared="None"),
        )
    with pytest.raises(ValidationError, match="Unknown effects"):
        Effect(value=EffectValue.FALSE)
    assert (
        Effect(value=EffectValue.FALSE, evidence=Evidence.INFERRED).value
        == EffectValue.FALSE
    )

"""Signing needs its own authority, before any key/tool/network access."""

import builtins
import copy
import io
import json
import os
import socket
import subprocess

import pytest
from test_operator_policy import (
    arguments,
    document,
    policy,
    record,
)
from test_operator_policy import (
    installed as installed,
)

from apizr.cli import main
from apizr.local_plugins import run_extension
from apizr.operator_policy import (
    AuthorizationDenied,
    OperatorPolicy,
    decide,
    tsa_identity,
)
from apizr.publication_contracts import AttestRequest, Docker

pytestmark = pytest.mark.timeout(30)
CASES = [
    ("missing", "operator_policy_required"),
    ("invalid", "operator_policy_invalid"),
    ("publication", "operator_operation_denied"),
    ("plugin", "operator_identity_denied"),
    ("dependency", "operator_identity_denied"),
    ("repository", "operator_repository_denied"),
    ("key_id", "operator_key_denied"),
    ("expected_signer", "operator_key_denied"),
    ("key_file", "operator_key_denied"),
    ("tsa_host", "operator_tsa_denied"),
    ("tsa_port", "operator_tsa_denied"),
    ("tsa_path", "operator_tsa_denied"),
    ("tsa_prefix", "operator_tsa_denied"),
    ("tsa_scheme", "operator_tsa_denied"),
    ("read_only", "operator_permissions_denied"),
    ("no_timestamp", "operator_permissions_denied"),
    ("no_read", "operator_permissions_denied"),
    ("no_sign", "operator_permissions_denied"),
    ("argument_policy", "operator_arguments_invalid"),
]


def altered(binding, case):
    raw, args = document(binding, "attest"), arguments("attest")
    grant = raw["grants"][0]
    if case == "publication":
        return document(binding, "publish"), args
    if case == "invalid":
        raw["schema"] = "unsupported"
    if case == "plugin":
        grant["plugin"]["sha256"] = "f" * 64
    if case == "dependency":
        # The real fixture has no dependencies; alter the locked closure itself.
        grant["plugin"]["lock_sha256"] = "f" * 64
        grant["plugin"]["dependencies"] = [
            {"name": "substituted", "version": "1.0", "sha256": "f" * 64}
        ]
    if case == "repository":
        grant["repository"] += "-other"
    if case in {"key_id", "expected_signer"}:
        grant[case] = "f" * len(grant[case])
    if case == "key_file":
        grant[case] = "/private/other.key"
    urls = {
        "tsa_host": "https://other.example:8443/timestamp",
        "tsa_port": "https://tsa.example:8444/timestamp",
        "tsa_path": "https://tsa.example:8443/other",
        "tsa_prefix": "https://tsa.example:8443/timestamp-other",
        "tsa_scheme": "http://tsa.example:8443/timestamp",
    }
    if case in urls:
        grant["tsa_url"] = urls[case]
    permissions = {
        "read_only": ["registry.read"],
        "no_timestamp": ["registry.read", "receipt.sign"],
        "no_read": ["receipt.sign", "timestamp.request"],
        "no_sign": ["registry.read", "timestamp.request"],
    }
    if case in permissions:
        grant["permissions"] = permissions[case]
    if case == "argument_policy":
        args["operator_policy"] = document(binding, "attest")
    return raw, args


@pytest.mark.parametrize("installed", ["attest"], indirect=True)
@pytest.mark.parametrize("case,code", CASES)
def test_signing_cli_and_api_refuse_before_effect(
    installed, case, code, monkeypatch, tmp_path, capsys
):
    root, binding, _, marker = installed
    raw, args = altered(binding, case)
    selected = (
        OperatorPolicy.model_construct(schema_version="unsupported", grants=())
        if case == "invalid"
        else None
        if case == "missing"
        else policy(raw)
    )
    path, selected_path = tmp_path / "args.json", tmp_path / "operator.json"
    path.write_text(json.dumps(args))
    selected_path.write_text(json.dumps(raw))
    before = {
        name: (root / name).read_bytes()
        for name in ("installations.json", "activations.json")
    }
    # Project, catalog, profile and environment cannot supply or enlarge authority.
    trusted = document(binding, "attest")
    (tmp_path / "apizr.toml").write_text('operator_policy = "operator.json"')
    (tmp_path / "catalog.json").write_text(json.dumps(trusted))
    (tmp_path / "profile.json").write_text(json.dumps(trusted))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APIZR_OPERATOR_POLICY", str(selected_path))

    def forbidden(*args, **kwargs):
        raise AssertionError("effect before authorization")

    original_open = os.open

    def checked(path, *args, **kwargs):
        assert str(path) not in {
            "/private/signing.key",
            "/private/credentials.json",
            "/daemon/docker.sock",
        }
        return original_open(path, *args, **kwargs)

    def guard_file(original):
        def read(path, *args, **kwargs):
            assert str(path) not in {
                "/private/signing.key",
                "/private/credentials.json",
                "/daemon/docker.sock",
            }
            return original(path, *args, **kwargs)

        return read

    monkeypatch.setattr(builtins, "open", guard_file(builtins.open))
    monkeypatch.setattr(io, "open", guard_file(io.open))
    monkeypatch.setattr(os, "open", checked)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    with pytest.raises(AuthorizationDenied) as error:
        run_extension(
            binding.name, "attest", args, directory=root, operator_policy=selected
        )
    assert error.value.code == code
    assert (
        main(
            [
                "plugins",
                "run",
                binding.name,
                "attest",
                "--arguments",
                str(path),
                "--plugins-dir",
                str(root),
                *(
                    []
                    if case == "missing"
                    else ["--operator-policy", str(selected_path)]
                ),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == error.value.decision.model_dump(by_alias=True)
    assert not marker.exists()
    assert all((root / name).read_bytes() == value for name, value in before.items())


@pytest.mark.parametrize("case,code", [c for c in CASES if c[0] != "invalid"])
def test_signing_decision_is_pure(case, code, monkeypatch):
    binding = record("attest")
    raw, args = altered(binding, case)
    selected = None if case == "missing" else policy(raw)

    def forbidden(*args, **kwargs):
        raise AssertionError("decision performed I/O")

    for owner, name in [(os, "open"), (subprocess, "Popen"), (socket, "socket")]:
        monkeypatch.setattr(owner, name, forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    assert decide(selected, binding, "attest", args).code == code


def test_signing_and_publication_are_independent():
    binding = record("attest")
    signing = policy(document(binding, "attest"))
    publication = policy(document(binding, "publish"))
    assert (
        decide(signing, binding, "publish", arguments("publish")).code
        == "operator_operation_denied"
    )
    assert (
        decide(publication, binding, "attest", arguments("attest")).code
        == "operator_operation_denied"
    )
    assert decide(signing, binding, "attest", arguments("attest")).allowed
    assert decide(None, binding, "verify", {}).code == "not_required"


@pytest.mark.parametrize(
    "left,right",
    [
        ("HTTPS://TSA.EXAMPLE/timestamp", "https://tsa.example:443/timestamp"),
        ("http://tsa.example", "http://tsa.example:80/"),
        ("http://[::1]:8800/tsa", "http://[::1]:8800/tsa"),
    ],
)
def test_authority_normalization(left, right):
    assert tsa_identity(left) == tsa_identity(right)
    binding, args = record("attest"), arguments("attest")
    raw = document(binding, "attest")
    raw["grants"][0]["tsa_url"] = left
    args["tsa_url"] = right
    assert decide(policy(raw), binding, "attest", args).allowed


@pytest.mark.parametrize(
    "url",
    [
        "ftp://tsa.example/",
        "https://u:p@tsa.example/",
        "https://tsa.example/?token=secret",
        "https://tsa.example/#x",
        "https://tsa.example:99999/",
        "https://tsa.example:0/",
        "https://tsa.example\\other/",
        "https://tsa%2eexample/",
        "https://tsa.example/\x00",
        "https://tsa.example/" + "a" * 2048,
    ],
)
def test_ambiguous_authorities_refused(url):
    with pytest.raises(ValueError):
        tsa_identity(url)


def test_path_and_encoding_are_not_prefix_or_decoded_aliases():
    assert tsa_identity("https://tsa.example/%74sa") != tsa_identity(
        "https://tsa.example/tsa"
    )
    binding = record("attest")
    raw, args = document(binding, "attest"), arguments("attest")
    args["key_file"] = "/private/./signing.key"
    assert decide(policy(raw), binding, "attest", args).code == "operator_key_denied"


def test_unvalidated_models_cannot_supply_authority():
    binding, args = record("attest"), arguments("attest")
    selected = policy(document(binding, "attest"))
    broken = selected.model_copy(
        update={
            "grants": (selected.grants[0].model_copy(update={"key_file": "relative"}),)
        }
    )
    assert decide(broken, binding, "attest", args).code == "operator_policy_invalid"
    bad_record = binding.model_copy(update={"version": True})
    assert (
        decide(selected, bad_record, "attest", args).code == "operator_identity_denied"
    )
    request = AttestRequest.model_construct(**args)
    assert (
        decide(selected, binding, "attest", request).code
        == "operator_arguments_invalid"
    )
    invalid = copy.deepcopy(args)
    invalid["docker"] = Docker.model_construct(executable="relative", socket="/socket")
    assert (
        decide(selected, binding, "attest", invalid).code
        == "operator_arguments_invalid"
    )


def test_signing_rule_is_strict_and_not_composed_from_partial_grants():
    binding = record("attest")
    raw = document(binding, "attest")
    raw["grants"] *= 2
    raw["grants"] = copy.deepcopy(raw["grants"])
    raw["grants"][0] = raw["grants"][0] | {
        "permissions": ["registry.read", "receipt.sign"]
    }
    raw["grants"][1] = raw["grants"][1] | {"permissions": ["timestamp.request"]}
    assert (
        decide(policy(raw), binding, "attest", arguments("attest")).code
        == "operator_permissions_denied"
    )
    for field, value in [
        ("permissions", ["receipt.sign", "receipt.sign"]),
        ("permissions", ["registry.publish"]),
        ("key_file", "relative"),
        ("secret", "content"),
        ("key_id", True),
    ]:
        altered = document(binding, "attest")
        altered["grants"][0][field] = value
        with pytest.raises(ValueError):
            policy(altered)

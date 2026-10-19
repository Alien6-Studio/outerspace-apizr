"""Request-selected verifiers and trust roots cannot enlarge operator authority."""

import builtins
import copy
import io
import json
import os
import socket
import subprocess

import pytest
from test_operator_policy import arguments, document, policy, record
from test_operator_policy import installed as installed

from apizr.cli import main
from apizr.contracts.publication import PublishRequest
from apizr.plugins.local import run_extension
from apizr.workspace.operator_policy import AuthorizationDenied, decide

CASES = (
    "tool_path",
    "tool_hash",
    "signer",
    "trust_path",
    "trust_hash",
    "unpinned",
    "legacy",
)


def substituted(binding, operation, change):
    raw, args = document(binding, operation), arguments(operation)
    if change == "tool_path":
        args["tool"]["executable"] = "/different/attest"
    if change == "tool_hash":
        args["tool"]["sha256"] = "d" * 64
    if change == "signer":
        args["expected_signer"] = "d" * 64
    if change == "trust_path":
        args["trust_store"] = "/different/trust"
    if change == "trust_hash":
        args["trust_store_sha256"] = "d" * 64
    if change == "unpinned":
        del args["trust_store_sha256"]
    if change == "legacy":
        del raw["grants"][0]["verification"]
    return raw, args


@pytest.mark.parametrize("operation", ["attest", "publish", "admit"])
@pytest.mark.parametrize("change", CASES)
def test_verification_authority_is_exact_and_pure(operation, change, monkeypatch):
    binding = record(operation)
    raw, args = substituted(binding, operation, change)
    selected = policy(raw)

    def forbidden(*args, **kwargs):
        raise AssertionError("authorization must perform no I/O")

    for module in (builtins, io, os):
        monkeypatch.setattr(module, "open", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    decision = decide(selected, binding, operation, args)
    assert not decision.allowed
    assert decision.code == (
        "operator_key_denied"
        if operation == "attest" and change == "signer"
        else "operator_verification_denied"
    )


@pytest.mark.parametrize("installed", ["attest", "publish", "admit"], indirect=True)
@pytest.mark.parametrize("change", CASES)
def test_verifier_substitution_refused_at_managed_cli_and_api(
    installed, change, monkeypatch, tmp_path, capsys
):
    root, binding, operation, marker = installed
    raw, args = substituted(binding, operation, change)
    selected = policy(raw)
    args_path, policy_path = tmp_path / "args.json", tmp_path / "operator.json"
    args_path.write_text(json.dumps(args))
    policy_path.write_text(json.dumps(raw))

    def forbidden(*args, **kwargs):
        raise AssertionError("effect before authorization")

    def guarded(original):
        def opened(path, *args, **kwargs):
            assert not str(path).startswith(
                ("/private/", "/native/", "/proof/", "/different/")
            ) or str(path).startswith(str(tmp_path))
            return original(path, *args, **kwargs)

        return opened

    # Permit the installed store and explicit argument/policy files only.
    for module in (builtins, io, os):
        monkeypatch.setattr(module, "open", guarded(module.open))
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    with pytest.raises(AuthorizationDenied) as error:
        run_extension(
            binding.name, operation, args, directory=root, operator_policy=selected
        )
    assert (
        main(
            [
                "plugins",
                "run",
                binding.name,
                operation,
                "--arguments",
                str(args_path),
                "--operator-policy",
                str(policy_path),
                "--plugins-dir",
                str(root),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == error.value.decision.model_dump(by_alias=True)
    assert not marker.exists()


@pytest.mark.parametrize("operation", ["attest", "publish", "admit"])
def test_verification_and_permissions_must_belong_to_the_same_grant(operation):
    binding, args = record(operation), arguments(operation)
    raw = document(binding, operation)
    complete = copy.deepcopy(raw["grants"][0])
    complete["verification"]["tool"]["sha256"] = "d" * 64
    raw["grants"][0]["permissions"] = ["registry.read"]
    raw["grants"].append(complete)
    assert (
        decide(policy(raw), binding, operation, args).code
        == "operator_permissions_denied"
    )


def test_unpinned_historical_verification_request_keeps_its_serialized_shape():
    from apizr.contracts.publication import VerifyRequest

    raw = arguments("publish")
    del raw["transport"], raw["trust_store_sha256"]
    raw["schema"] = "apizr.verify-delivery/v1"
    observed = VerifyRequest.model_validate(raw).model_dump(by_alias=True)
    assert "trust_store_sha256" not in observed
    assert observed.items() >= raw.items()
    # The same old input remains readable for migration, but is not a grant.
    raw["schema"] = "apizr.publish-proof/v1"
    raw["transport"] = arguments("publish")["transport"]
    assert PublishRequest.model_validate(raw).trust_store_sha256 is None

"""Managed OCI construction needs exact, independent operator authorization."""

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
from apizr.operator_policy import AuthorizationDenied, OperatorPolicy, decide
from apizr.plugins.local import run_extension
from apizr.publication_contracts import BuildRequest, BuildTarget, Docker

pytestmark = pytest.mark.timeout(30)
CASES = [
    ("missing", "operator_policy_required"),
    ("invalid", "operator_policy_invalid"),
    ("publication", "operator_operation_denied"),
    ("signing", "operator_operation_denied"),
    ("identity", "operator_identity_denied"),
    ("dependency", "operator_identity_denied"),
    *[
        (field, "operator_build_denied")
        for field in (
            "base_image",
            "digest",
            "platform",
            "interface",
            "tag",
            "bundle",
            "requirements",
            "wheelhouse",
            "socket",
            "executable",
            "buildx",
            "prefix",
        )
    ],
    ("read_only", "operator_permissions_denied"),
    ("build_only", "operator_permissions_denied"),
    ("argument_policy", "operator_arguments_invalid"),
]


def altered(binding, case):
    raw, args = document(binding, "build"), arguments("build")
    grant = raw["grants"][0]
    if case == "publication":
        return document(binding, "push"), args
    if case == "signing":
        return document(binding, "attest"), args
    if case == "invalid":
        raw["schema"] = "unsupported"
    if case == "identity":
        grant["plugin"]["sha256"] = "f" * 64
    if case == "dependency":
        grant["plugin"]["lock_sha256"] = "f" * 64
        grant["plugin"]["dependencies"] = [
            {"name": "substituted", "version": "1.0", "sha256": "f" * 64}
        ]
    changes = {
        "base_image": "other:3.14@sha256:" + "c" * 64,
        "digest": "python:3.14-slim@sha256:" + "d" * 64,
        "platform": "linux/arm64",
        "interface": "mcp",
        "tag": "service:reviewed-other",
        "bundle": "/inputs/bundle-other",
        "requirements": "/inputs/other.lock",
        "wheelhouse": "/inputs/wheels-other",
        "prefix": "/inputs/bundle/subdir",
    }
    if case in changes:
        key = {"digest": "base_image", "prefix": "bundle"}.get(case, case)
        args[key] = changes[case]
    if case in {"socket", "executable", "buildx"}:
        args["docker"][case] = "/native/other"
    if case in {"read_only", "build_only"}:
        grant["permissions"] = [
            "registry.read" if case == "read_only" else "image.build"
        ]
    if case == "argument_policy":
        args["operator_policy"] = document(binding, "build")
    return raw, args


@pytest.mark.parametrize("installed", ["build"], indirect=True)
@pytest.mark.parametrize("case,code", CASES)
def test_build_cli_and_api_refuse_before_effect(
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
    path, operator = tmp_path / "build.json", tmp_path / "operator.json"
    path.write_text(json.dumps(args))
    operator.write_text(json.dumps(raw))
    before = {
        name: (root / name).read_bytes()
        for name in ("installations.json", "activations.json")
    }
    (tmp_path / "apizr.toml").write_text('operator_policy = "operator.json"')
    for name in ("catalog.json", "profile.json"):
        (tmp_path / name).write_text(json.dumps(document(binding, "build")))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APIZR_OPERATOR_POLICY", str(operator))

    def forbidden(*args, **kwargs):
        raise AssertionError("effect before build authorization")

    def guard(original):
        def checked(path, *args, **kwargs):
            assert not str(path).startswith(("/inputs", "/native", "/daemon"))
            return original(path, *args, **kwargs)

        return checked

    for owner, name in [
        (builtins, "open"),
        (io, "open"),
        (os, "open"),
        (os, "scandir"),
        (os, "listdir"),
        (os, "stat"),
    ]:
        monkeypatch.setattr(owner, name, guard(getattr(owner, name)))
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    with pytest.raises(AuthorizationDenied) as error:
        run_extension(
            binding.name, "build", args, directory=root, operator_policy=selected
        )
    assert error.value.code == code
    assert (
        main(
            [
                "plugins",
                "run",
                binding.name,
                "build",
                "--arguments",
                str(path),
                "--plugins-dir",
                str(root),
                *([] if case == "missing" else ["--operator-policy", str(operator)]),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == "" and json.loads(
        captured.err
    ) == error.value.decision.model_dump(by_alias=True)
    assert not marker.exists()
    assert all((root / name).read_bytes() == value for name, value in before.items())


@pytest.mark.parametrize(
    "case,code",
    [c for c in CASES if c[0] != "invalid"] + [("authorized", "authorized")],
)
def test_build_decision_is_pure(case, code, monkeypatch):
    binding = record("build")
    raw, args = altered(binding, case)
    selected = None if case == "missing" else policy(raw)

    def forbidden(*args, **kwargs):
        raise AssertionError("decision performed external I/O")

    with monkeypatch.context() as checks:
        for owner, name in [
            (builtins, "open"),
            (io, "open"),
            (os, "open"),
            (os, "stat"),
            (os, "scandir"),
            (subprocess, "Popen"),
            (socket, "socket"),
        ]:
            checks.setattr(owner, name, forbidden)
        result = decide(selected, binding, "build", args)
    assert result.code == code


@pytest.mark.parametrize(
    "image",
    [
        "python@sha256:",
        "python:3.14-slim@sha256:",
        "docker.io/library/python@sha256:",
        "registry.example:5443/team/base@sha256:",
    ],
)
@pytest.mark.parametrize("interface", ["rest", "mcp"])
def test_existing_base_forms_and_interfaces_still_work(image, interface):
    binding, args = record("build"), arguments("build")
    raw = document(binding, "build")
    args["base_image"] = raw["grants"][0]["target"]["base_image"] = image + "c" * 64
    args["interface"] = raw["grants"][0]["target"]["interface"] = interface
    args["timeout_ms"], args["max_log_bytes"] = 360000, 2048
    assert BuildRequest.model_validate(args).base_image == args["base_image"]
    assert decide(policy(raw), binding, "build", args).allowed


def test_build_grants_do_not_authorize_publication_or_signing():
    binding = record("build")
    selected = policy(document(binding, "build"))
    assert (
        decide(selected, binding, "push", arguments("push")).code
        == "operator_operation_denied"
    )
    assert (
        decide(selected, record("attest"), "attest", arguments("attest")).code
        == "operator_identity_denied"
    )
    assert decide(None, record("attest"), "verify", {}).code == "not_required"


def test_build_grants_and_arguments_revalidate_unconstructed_objects():
    binding, args = record("build"), arguments("build")
    selected = policy(document(binding, "build"))
    target = BuildTarget.model_construct(**args).model_copy(
        update={"bundle": "relative"}
    )
    broken = selected.model_copy(
        update={"grants": (selected.grants[0].model_copy(update={"target": target}),)}
    )
    assert decide(broken, binding, "build", args).code == "operator_policy_invalid"
    args["docker"] = Docker.model_construct(
        executable="relative", socket="/daemon/socket"
    )
    assert decide(selected, binding, "build", args).code == "operator_arguments_invalid"


def test_build_rule_strict_and_permissions_not_combined():
    binding, raw = record("build"), document(record("build"), "build")
    raw["grants"].append(copy.deepcopy(raw["grants"][0]))
    raw["grants"][0]["permissions"] = ["registry.read"]
    raw["grants"][1]["permissions"] = ["image.build"]
    assert (
        decide(policy(raw), binding, "build", arguments("build")).code
        == "operator_permissions_denied"
    )
    for field, value in [
        ("permissions", ["image.build", "image.build"]),
        ("permissions", ["registry.publish"]),
        ("repository", "registry.example/team/service"),
    ]:
        invalid = document(binding, "build")
        invalid["grants"][0][field] = value
        with pytest.raises(ValueError):
            policy(invalid)
    for field, value in [
        ("bundle", "relative"),
        ("base_image", "python:latest"),
        ("interface", "unknown"),
        ("inputs_sha256", "a" * 64),
        ("command", "free-form"),
    ]:
        invalid = document(binding, "build")
        invalid["grants"][0]["target"][field] = value
        with pytest.raises(ValueError):
            policy(invalid)

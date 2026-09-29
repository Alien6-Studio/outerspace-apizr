"""Operator admission precedes native tools, registry credentials and plugin code."""

import copy
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from apizr.cli import main
from apizr.extension_runtime import Limits, SizeLimitExceeded
from apizr.local_plugins import (
    activation,
    enable_extension,
    install_extension,
    run_extension,
)
from apizr.local_plugins.models import Installation
from apizr.operator_policy import (
    MAX_POLICY_BYTES,
    AuthorizationDenied,
    OperatorPolicy,
    PluginIdentity,
    decide,
    load_operator_policy,
    repository_name,
)
from apizr.publication_contracts import PublishRequest, PushRequest

pytestmark = pytest.mark.timeout(30)
REPOSITORY = "registry.example:5443/team/service"


def arguments(operation):
    if operation == "build":
        return {
            "schema": "apizr.oci-build/v1",
            "bundle": "/inputs/bundle",
            "interface": "rest",
            "base_image": "python:3.14-slim@sha256:" + "c" * 64,
            "platform": "linux/amd64",
            "tag": "service:reviewed",
            "requirements": "/inputs/requirements.lock",
            "wheelhouse": "/inputs/wheels",
            "docker": {"executable": "/native/docker", "socket": "/daemon/docker.sock"},
        }
    if operation == "push":
        return {
            "schema": "apizr.oci-push/v1",
            "image_id": "sha256:" + "a" * 64,
            "platform": "linux/amd64",
            "inputs_sha256": "b" * 64,
            "destination": REPOSITORY + ":v1",
            "docker": {"executable": "/native/docker", "socket": "/daemon/docker.sock"},
            "authentication": {"config_file": "/private/credentials.json"},
        }
    if operation == "admit":
        data = arguments("publish")
        data.pop("proof_dir")
        return data | {
            "schema": "apizr.admit-delivery/v1",
            "push_result": "/proof/push.json",
            "delivery_manifest": {
                "delivery_plan_digest": {"algorithm": "sha256", "value": "a" * 64},
                "image_id": "sha256:" + "a" * 64,
                "inputs_sha256": "b" * 64,
                "platform": "linux/amd64",
            },
            "destination": REPOSITORY + ":v1",
            "artifact_reference": REPOSITORY + "@sha256:" + "d" * 64,
            "docker": {"executable": "/native/docker", "socket": "/daemon/docker.sock"},
        }
    if operation == "attest":
        data = arguments("publish")
        del data["proof_dir"], data["transport"]
        return data | {
            "schema": "apizr.attest-delivery/v1",
            "build_result": "/proof/build.json",
            "push_result": "/proof/push.json",
            "docker": {"executable": "/native/docker", "socket": "/daemon/docker.sock"},
            "authentication": {"config_file": "/private/credentials.json"},
            "key_file": "/private/signing.key",
            "key_id": "e" * 32,
            "tsa_url": "https://tsa.example:8443/timestamp",
            "output_dir": "/proof/output",
        }
    return {
        "schema": "apizr.publish-proof/v1",
        "expected_reference": REPOSITORY + "@sha256:" + "a" * 64,
        "expected_signer": "b" * 64,
        "trust_store": "/proof/trust",
        "proof_dir": "/proof/signed",
        "tool": {
            "executable": "/native/attest",
            "version": "0.1.0",
            "sha256": "c" * 64,
        },
        "transport": {
            "tool": {
                "executable": "/native/oras",
                "version": "1.3.4",
                "sha256": "d" * 64,
            },
            "authentication": {"config_file": "/private/credentials.json"},
        },
    }


def record(operation="push"):
    name, module = (
        ("outerspace-apizr-oci", "apizr_oci.protocol")
        if operation in {"push", "build"}
        else ("outerspace-apizr-attest", "apizr_attest.protocol")
    )
    return Installation.model_validate(
        {
            "schema": "apizr.extension-manifest/v1",
            "name": name,
            "version": "0.0.0",
            "module": module,
            "protocol": "apizr.extension/v1",
            "sha256": "a" * 64,
            "environment_id": "b" * 32,
            "python": "/installation/bin/python",
            "lock_sha256": "c" * 64,
            "dependencies": [{"name": "support", "version": "1.0", "sha256": "d" * 64}],
        }
    )


def document(binding, operation="push", repository=REPOSITORY):
    result = {
        "schema": "apizr.operator-policy/v1",
        "grants": [
            {
                "plugin": PluginIdentity.from_installation(binding).model_dump(
                    mode="json"
                ),
                "operation": operation,
                "repository": repository,
                "permissions": ["registry.read", "registry.publish"],
            }
        ],
    }
    if operation == "build":
        del result["grants"][0]["repository"]
        result["grants"][0]["target"] = {
            k: v for k, v in arguments(operation).items() if k != "schema"
        }
        result["grants"][0]["permissions"] = ["image.build", "registry.read"]
    if operation == "attest":
        result["grants"][0].update(
            {
                k: arguments(operation)[k]
                for k in ("key_id", "expected_signer", "key_file", "tsa_url")
            }
        )
        result["grants"][0]["permissions"] = [
            "registry.read",
            "receipt.sign",
            "timestamp.request",
        ]
    return result


def policy(value):
    return OperatorPolicy.model_validate_json(json.dumps(value), strict=True)


@pytest.mark.parametrize("operation", ["push", "publish", "admit"])
@pytest.mark.parametrize(
    "change,code",
    [
        ("missing", "operator_policy_required"),
        ("empty", "operator_identity_denied"),
        ("name", "operator_identity_denied"),
        ("version", "operator_identity_denied"),
        ("sha256", "operator_identity_denied"),
        ("lock_sha256", "operator_identity_denied"),
        ("dependency", "operator_identity_denied"),
        ("operation", "operator_operation_denied"),
        ("registry", "operator_repository_denied"),
        ("port", "operator_repository_denied"),
        ("prefix", "operator_repository_denied"),
        ("repository", "operator_repository_denied"),
        ("read-only", "operator_permissions_denied"),
        ("write-only", "operator_permissions_denied"),
    ],
)
def test_exact_grants_without_external_io(operation, change, code, monkeypatch):
    binding, args = record(operation), arguments(operation)
    raw = document(binding, operation)
    grant = raw["grants"][0]
    if change == "empty":
        raw["grants"] = []
    if change == "name":
        grant["plugin"]["name"] = "another-plugin"
    if change == "version":
        grant["plugin"]["version"] = "0.0.1"
    if change in ("sha256", "lock_sha256"):
        grant["plugin"][change] = "e" * 64
    if change == "dependency":
        grant["plugin"]["dependencies"][0]["sha256"] = "e" * 64
    if change == "operation":
        grant["operation"] = "publish" if operation == "push" else "push"
    if change == "registry":
        grant["repository"] = "other.example:5443/team/service"
    if change == "port":
        grant["repository"] = "registry.example:5444/team/service"
    if change == "prefix":
        field = "destination" if operation == "push" else "expected_reference"
        args[field] = args[field].replace("/service", "/service-other")
        if operation == "admit":
            for key in ("destination", "artifact_reference"):
                args[key] = args[key].replace("/service", "/service-other")
    if change == "repository":
        grant["repository"] = "registry.example:5443/team/other"
    if change == "read-only":
        grant["permissions"] = ["registry.read"]
    if change == "write-only":
        grant["permissions"] = ["registry.publish"]
    selected = None if change == "missing" else policy(raw)

    def forbidden(*args, **kwargs):
        pytest.fail("decision performed external I/O")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    decision = decide(selected, binding, operation, args)
    assert not decision.allowed and decision.code == code
    assert "/private" not in decision.model_dump_json()


@pytest.mark.parametrize("operation", ["push", "publish"])
@pytest.mark.parametrize(
    "repository",
    [
        REPOSITORY,
        "docker.io/library/service",
        "index.docker.io/library/service",
        "registry.example:443/team/service",
    ],
)
def test_authorized_tags_digests_and_hub_aliases(operation, repository):
    binding, args = record(operation), arguments(operation)
    field = "destination" if operation == "push" else "expected_reference"
    args[field] = repository + (
        ":different-tag" if operation == "push" else "@sha256:" + "f" * 64
    )
    selected = policy(document(binding, operation, repository_name(repository)))
    assert decide(selected, binding, operation, args).code == "authorized"


@pytest.mark.parametrize(
    "repository",
    [
        "alpine",
        "team/service",
        "registry.example/team/service:tag",
        "registry.example/team/service@sha256:" + "a" * 64,
        "registry.example/team/*",
        "registry.example/team/service%2fother",
        "registry.example/team/../service",
        "user:password@registry.example/team/service",
        "https://registry.example/team/service",
        "registry.example:05443/team/service",
        "registry.example:65536/team/service",
        "registry.example/team/service\n",
    ],
)
def test_policy_rejects_ambiguous_repositories(repository):
    with pytest.raises(ValueError):
        policy(document(record(), repository=repository))


@pytest.mark.parametrize("operation", ["push", "publish"])
@pytest.mark.parametrize(
    "change",
    ["extra", "destination", "bool-timeout", "schema", "inline-secret", "private-key"],
)
def test_shared_contract_validation(operation, change):
    binding, args = record(operation), arguments(operation)
    if change == "extra":
        args["operator_policy"] = document(binding, operation)
    if change == "destination":
        args["destination" if operation == "push" else "expected_reference"] = (
            "ambiguous"
        )
    if change == "bool-timeout":
        args["timeout_ms"] = True
    if change == "schema":
        args["schema"] += "-unknown"
    if change == "inline-secret":
        args["password"] = "SECRET"
    if change == "private-key":
        args["key_file"] = "/private/signing.key"
    with pytest.raises(ValueError):
        (PushRequest if operation == "push" else PublishRequest).model_validate(args)
    assert (
        decide(policy(document(binding, operation)), binding, operation, args).code
        == "operator_arguments_invalid"
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b"{}",
        b'{"schema":"unknown","grants":[]}',
        b'{"schema":"apizr.operator-policy/v1","grants":[],"extra":true}',
        b'{"schema":"apizr.operator-policy/v1","grants":[],"grants":[]}',
        b"\xff",
        b"[" * 2000,
    ],
)
def test_invalid_policy_files(tmp_path, raw):
    path = tmp_path / "operator.json"
    path.write_bytes(raw)
    with pytest.raises(AuthorizationDenied, match="operator_policy_invalid"):
        load_operator_policy(path)


def test_bounded_regular_policy_files(tmp_path):
    path = tmp_path / "operator.json"
    with pytest.raises(AuthorizationDenied, match="unavailable"):
        load_operator_policy(path)
    path.write_bytes(b" " * (MAX_POLICY_BYTES + 1))
    with pytest.raises(AuthorizationDenied, match="too_large"):
        load_operator_policy(path)
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(AuthorizationDenied, match="invalid"):
        load_operator_policy(path)
    path.unlink()
    path.symlink_to(tmp_path / "elsewhere")
    with pytest.raises(AuthorizationDenied, match="unavailable"):
        load_operator_policy(path)


@pytest.fixture(params=["push", "publish", "attest", "build", "admit"])
def installed(request, wheel_factory, tmp_path):
    operation = request.param
    template = record(operation)
    marker = tmp_path / "plugin-executed"
    # The fixture uses the official identity/module and a real isolated wheel.
    module_path = template.module.replace(".", "/") + ".py"
    source = (
        "import json,sys\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).touch()\n"
        "r=json.load(sys.stdin)\nprint(json.dumps({k:r[k] for k in ('protocol','request_id','operation')}|{'status':'ok','result':r['arguments']}))\n"
    ).encode()
    wheel, digest = wheel_factory(
        name=template.name,
        version=template.version,
        manifest_changes={"module": template.module},
        files={
            template.module.split(".")[0] + "/__init__.py": b"",
            module_path: source,
        },
    )
    root = tmp_path / "plugins"
    binding = install_extension(wheel, digest, directory=root)
    enable_extension(binding.name, binding.version, directory=root)
    return root, binding, operation, marker


def test_managed_cli_and_api_refuse_before_effect(
    installed, tmp_path, monkeypatch, capsys
):
    root, binding, operation, marker = installed
    args = arguments(operation)
    path = tmp_path / "arguments.json"
    path.write_text(json.dumps(args))
    inventory = (root / "installations.json").read_bytes()
    active = (root / "activations.json").read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized plugin or network started")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    original_open = os.open

    def checked(path, *args, **kwargs):
        assert str(path) not in {"/private/credentials.json", "/private/signing.key"}
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", checked)
    # Project/catalog/profile and environment variables have no authority.
    raw = document(binding, operation)
    selected = tmp_path / "operator.json"
    selected.write_text(json.dumps(raw))
    monkeypatch.setenv("APIZR_OPERATOR_POLICY", str(selected))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "apizr.toml").write_text('operator_policy = "operator.json"')
    (tmp_path / "catalog.json").write_text(json.dumps(raw))
    for operator in (None, policy(raw | {"grants": []})):
        with pytest.raises(AuthorizationDenied) as error:
            run_extension(
                binding.name, operation, args, directory=root, operator_policy=operator
            )
        selected.write_text(json.dumps(raw | {"grants": []}))
        options = [] if operator is None else ["--operator-policy", str(selected)]
        assert (
            main(
                [
                    "plugins",
                    "run",
                    binding.name,
                    operation,
                    "--arguments",
                    str(path),
                    "--plugins-dir",
                    str(root),
                    *options,
                ]
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert json.loads(captured.err) == error.value.decision.model_dump(
            by_alias=True
        )
    assert not marker.exists()
    assert (root / "installations.json").read_bytes() == inventory
    assert (root / "activations.json").read_bytes() == active


def test_authorized_call_uses_owned_snapshot(installed, tmp_path, monkeypatch):
    root, binding, operation, marker = installed
    args = arguments(operation)
    before = copy.deepcopy(args)
    path = tmp_path / "arguments.json"
    path.write_text(json.dumps(args))
    selected = policy(document(binding, operation))
    original = activation.invoke_extension

    def changed(*params, **kwargs):
        args.clear()
        args["destination"] = "other.example/team/stolen:v1"
        path.write_text(json.dumps(args))
        return original(*params, **kwargs)

    monkeypatch.setattr(activation, "invoke_extension", changed)
    result = run_extension(
        binding.name, operation, args, directory=root, operator_policy=selected
    )
    assert result.result == before and marker.exists()
    assert ("key_file" in before) == (operation == "attest")
    with pytest.raises(SizeLimitExceeded):
        run_extension(
            binding.name,
            operation,
            {"data": "x" * 10000},
            directory=root,
            limits=Limits(max_request_bytes=1024),
            operator_policy=selected,
        )


def test_official_module_alias_cannot_bypass():
    binding = record().model_copy(update={"name": "renamed-publisher"})
    assert (
        decide(None, binding, "push", arguments("push")).code
        == "operator_identity_denied"
    )
    binding = record().model_copy(update={"module": "replacement"})
    assert (
        decide(None, binding, "push", arguments("push")).code
        == "operator_identity_denied"
    )


@pytest.mark.parametrize("operation", ["verify", "discover", "fetch", "analyze"])
def test_other_operations_preserve_current_scope(operation):
    assert decide(None, record(), operation, {}).code == "not_required"


def test_core_import_does_not_load_plugins_or_optional_sdks(tmp_path):
    source = """import sys
from apizr.operator_policy import OperatorPolicy, decide
from apizr.local_plugins import run_extension
assert not any(n.split('.')[0] in {'apizr_oci','apizr_attest','apizr_mcp','docker','mcp','fastapi','oras'} for n in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_typed_policies_are_revalidated_and_bounded():
    binding = record()
    valid = policy(document(binding))
    changed = valid.model_copy(update={"schema_version": "unknown"})
    assert (
        decide(changed, binding, "push", arguments("push")).code
        == "operator_policy_invalid"
    )
    large_grant = valid.grants[0].model_copy(
        update={"repository": "registry.example/" + "long" * 30 + "/service"}
    )
    large = valid.model_copy(update={"grants": (large_grant,) * 128})
    assert (
        decide(large, binding, "push", arguments("push")).code
        == "operator_policy_too_large"
    )
    assert (
        decide({}, binding, "push", arguments("push")).code == "operator_policy_invalid"
    )


@pytest.mark.parametrize(
    "change",
    [
        "duplicate-dependency",
        "missing-lock",
        "name",
        "permissions",
        "unknown-operation",
        "unknown-identity",
    ],
)
def test_policy_identity_and_permissions_are_strict(change):
    raw = document(record())
    grant = raw["grants"][0]
    if change == "duplicate-dependency":
        grant["plugin"]["dependencies"] *= 2
    if change == "missing-lock":
        grant["plugin"]["lock_sha256"] = None
    if change == "name":
        grant["plugin"]["name"] = "APIZR_OCI"
    if change == "permissions":
        grant["permissions"] = ["registry.read", "registry.read"]
    if change == "unknown-operation":
        grant["operation"] = "sign"
    if change == "unknown-identity":
        grant["plugin"]["trust"] = True
    with pytest.raises(ValueError):
        policy(raw)


def test_dependency_order_does_not_change_exact_identity():
    binding = record().model_copy(
        update={
            "dependencies": [
                *record().dependencies,
                record().dependencies[0].model_copy(update={"name": "another"}),
            ]
        }
    )
    raw = document(binding)
    raw["grants"][0]["plugin"]["dependencies"].reverse()
    assert decide(policy(raw), binding, "push", arguments("push")).allowed


def test_shared_publication_models_are_the_plugin_contracts():
    # Loaded only by this plugin test, never during core invocation/authorization.
    import sys

    root = Path(__file__).parents[2]
    for name in ("oci", "attest"):
        path = str(root / "plugins" / name / "src")
        if path not in sys.path:
            sys.path.insert(0, path)
    from apizr_attest.model import AttestRequest as PluginAttest
    from apizr_attest.model import PublishRequest as PluginPublish
    from apizr_oci.model import BuildRequest as PluginBuild
    from apizr_oci.model import PushRequest as PluginPush

    from apizr.publication_contracts import BuildRequest

    assert PluginBuild is BuildRequest
    assert PluginPush is PushRequest
    from apizr.publication_contracts import AttestRequest

    assert PluginAttest is AttestRequest
    assert PluginPublish is PublishRequest


def test_authorized_cli_and_policy_do_not_replace_activation(
    installed, tmp_path, capsys
):
    from apizr.local_plugins import PluginError, disable_extension

    root, binding, operation, marker = installed
    selected = tmp_path / "operator.json"
    selected.write_text(json.dumps(document(binding, operation)))
    path = tmp_path / "arguments.json"
    path.write_text(json.dumps(arguments(operation)))
    assert (
        main(
            [
                "plugins",
                "run",
                binding.name,
                operation,
                "--arguments",
                str(path),
                "--operator-policy",
                str(selected),
                "--plugins-dir",
                str(root),
            ]
        )
        == 0
    )
    result = capsys.readouterr()
    assert result.err == "" and json.loads(result.out)["result"] == arguments(operation)
    assert marker.exists()
    disable_extension(binding.name, directory=root)
    with pytest.raises(PluginError, match="plugin_inactive"):
        run_extension(
            binding.name,
            operation,
            arguments(operation),
            directory=root,
            operator_policy=load_operator_policy(selected),
        )


def test_complete_documented_policy():
    selected = load_operator_policy(
        Path(__file__).parents[2] / "docs/examples/operator.json"
    )
    assert {(g.plugin.name, g.operation) for g in selected.grants} == {
        ("outerspace-apizr-oci", "push"),
        ("outerspace-apizr-oci", "build"),
        ("outerspace-apizr-attest", "publish"),
        ("outerspace-apizr-attest", "attest"),
    }


@pytest.mark.parametrize("operation", ["build", "attest", "push", "publish", "admit"])
def test_renamed_and_existing_plugins_require_separate_exact_grants(operation):
    renamed = record(operation)
    existing = renamed.model_copy(
        update={"name": renamed.name.removeprefix("outerspace-")}
    )
    for binding, other in ((renamed, existing), (existing, renamed)):
        assert decide(None, binding, operation, arguments(operation)).code == (
            "operator_policy_required"
        )
        granted = policy(document(binding, operation))
        assert decide(granted, binding, operation, arguments(operation)).allowed
        refused = decide(granted, other, operation, arguments(operation))
        assert not refused.allowed and refused.code == "operator_identity_denied"


@pytest.mark.parametrize("operation", ["build", "attest", "push", "publish", "admit"])
def test_git_grant_does_not_authorize_plugin_operations(operation):
    selected = OperatorPolicy.model_validate_json(
        json.dumps(
            {
                "schema": "apizr.operator-policy/v1",
                "grants": [
                    {
                        "adapter": "git",
                        "operation": "fetch",
                        "permissions": ["git.fetch"],
                        "target": {
                            "transport": "https",
                            "repository": "https://git.example/repo",
                            "reference": "main",
                        },
                    }
                ],
            }
        )
    )
    assert (
        decide(selected, record(operation), operation, arguments(operation)).code
        == "operator_identity_denied"
    )


def test_build_grant_binds_proof_requirement():
    binding = record("build")
    optional = policy(document(binding, "build"))
    required = arguments("build") | {"proof_requirement": "required"}
    assert not decide(optional, binding, "build", required).allowed
    raw = document(binding, "build")
    raw["grants"][0]["target"]["proof_requirement"] = "required"
    selected = policy(raw)
    assert decide(selected, binding, "build", required).allowed
    assert not decide(selected, binding, "build", arguments("build")).allowed


def test_signing_is_not_admission_permission():
    binding = record("admit")
    assert not decide(
        policy(document(binding, "attest")), binding, "admit", arguments("admit")
    ).allowed
    assert decide(
        policy(document(binding, "admit")), binding, "admit", arguments("admit")
    ).allowed

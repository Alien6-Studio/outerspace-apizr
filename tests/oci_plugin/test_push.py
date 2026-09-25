"""Publication identity, admission, state and credential isolation regressions."""

import base64
import copy
import hashlib
import importlib
import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

import pytest
from apizr_oci.model import BuildError, PushRequest
from apizr_oci.process import run
from apizr_oci.push import authentication, push

mod = importlib.import_module("apizr_oci.push")
CONFIG = "sha256:" + "a" * 64
INPUTS = "b" * 64
REGISTRY = "registry.test:5443"
DESTINATION = REGISTRY + "/services/rest:v1"
SECRET = "private-test-value"
MEDIA = "application/vnd.oci.image.manifest.v1+json"
MANIFEST = {
    "schemaVersion": 2,
    "mediaType": MEDIA,
    "config": {"digest": CONFIG},
    "layers": [],
}
RAW = json.dumps(MANIFEST).encode()
DIGEST = "sha256:" + hashlib.sha256(RAW).hexdigest()
REMOTE = {
    "Descriptor": {
        "digest": DIGEST,
        "mediaType": MEDIA,
        "platform": {"os": "linux", "architecture": "amd64"},
    },
    "OCIManifest": MANIFEST,
    "Raw": base64.b64encode(RAW).decode(),
}


@pytest.fixture
def request_data(tmp_path):
    auth = tmp_path / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "auths": {
                    REGISTRY: {
                        "auth": base64.b64encode(("user:" + SECRET).encode()).decode()
                    }
                }
            }
        )
    )
    return {
        "schema": "apizr.oci-push/v1",
        "image_id": CONFIG,
        "platform": "linux/amd64",
        "inputs_sha256": INPUTS,
        "destination": DESTINATION,
        "docker": {"executable": sys.executable, "socket": str(tmp_path / "socket")},
        "authentication": {"config_file": str(auth)},
    }


@pytest.mark.parametrize(
    "destination",
    [
        "image:v1",
        "registry.test/image:v1",
        "registry.test/ns/img",
        "https://registry.test/ns/img:v1",
        "registry.test:65536/ns/img:v1",
        "u:p@registry.test/ns/img:v1",
        "registry.test/ns/../img:v1",
        "registry.test/ns/img@sha256:" + "a" * 64,
        "registry.test/ns/img:v1\n",
        "--help",
        "registry.test/ns/IMG:v1",
    ],
)
def test_reference_refusals(request_data, destination):
    with pytest.raises(ValueError):
        PushRequest.model_validate(request_data | {"destination": destination})


@pytest.mark.parametrize(
    "change",
    [
        {"image_id": "mutable:tag"},
        {"inputs_sha256": "bad"},
        {"platform": "linux/ppc64"},
        {"timeout_ms": True},
        {"shell": "bad"},
        {"authentication": {"config_file": "relative"}},
    ],
)
def test_typed_refusals(request_data, change):
    with pytest.raises(ValueError):
        PushRequest.model_validate(request_data | change)


@pytest.fixture
def transport(request_data, tmp_path, monkeypatch):
    calls = []
    remote = {}
    image = {
        "Id": CONFIG,
        "Os": "linux",
        "Architecture": "amd64",
        "Config": {"User": "65532:65532", "Labels": {mod.LABEL: INPUTS}},
    }

    def docker(req, work, args, deadline, cancel=None, **kwargs):
        calls.append(args)
        assert SECRET not in str(args)
        if cancel is not None and cancel.is_set():
            raise BuildError("cancelled")
        if args[0] == "info":
            return b'{"IndexConfigs":{"docker.io":{"Secure":true}},"InsecureRegistryCIDRs":["127.0.0.0/8","::1/128"]}'
        if args[:2] == ["image", "inspect"]:
            assert args[2] == req.image_id
            return json.dumps([image]).encode()
        if args[:2] == ["manifest", "inspect"]:
            ref = args[-1]
            if ref not in remote:
                assert kwargs.get("absent_reference") == ref
                return b"null"
            value = remote[ref]
            if isinstance(value, Exception):
                raise value
            return json.dumps(value).encode()
        if args[:2] == ["image", "tag"]:
            assert args[2] == req.image_id
        elif args[:2] == ["image", "push"]:
            assert args[2:4] == ["--platform", "linux/amd64"]
            remote[args[-1]] = copy.deepcopy(REMOTE)
            remote[DESTINATION.rsplit(":", 1)[0] + "@" + DIGEST] = copy.deepcopy(REMOTE)
        elif args[:3] == ["buildx", "imagetools", "create"]:
            assert args[-1].endswith("@" + DIGEST)
            remote[DESTINATION] = copy.deepcopy(REMOTE)
        return b""

    monkeypatch.setattr(mod, "run", docker)
    with (
        TemporaryDirectory(prefix="az-push-") as directory,
        socket.socket(socket.AF_UNIX) as sock,
    ):
        request_data["docker"]["socket"] = directory + "/sock"
        sock.bind(request_data["docker"]["socket"])
        yield PushRequest.model_validate(request_data), calls, remote, image


def test_publish_repeat_and_immutable_selection(transport, tmp_path):
    request, calls, remote, image = transport
    result = push(request, workspace=tmp_path)
    assert (
        result.published
        and result.config_digest == CONFIG
        and result.manifest_digest == DIGEST
    )
    assert result.index_digest is None and result.image_id == CONFIG
    assert not list(tmp_path.glob("oci-push-*"))
    calls.clear()
    assert push(request, workspace=tmp_path) == result
    assert not any(c[:2] in (["image", "tag"], ["image", "push"]) for c in calls)
    # Containerd's immutable ID is a manifest, not a config digest.
    image["Id"] = DIGEST
    image["Descriptor"] = {"mediaType": MEDIA}
    assert (
        push(
            request.model_copy(update={"image_id": DIGEST}), workspace=tmp_path
        ).config_digest
        == CONFIG
    )


@pytest.mark.parametrize(
    "fault",
    [
        "id",
        "platform",
        "label",
        "user",
        "index",
        "absent",
        "auth",
        "remote-config",
        "remote-platform",
        "remote-index",
        "remote-raw",
        "remote-json",
        "post-upload",
        "verify",
        "cancel",
    ],
)
def test_refusals_and_unconfirmed_state(transport, tmp_path, monkeypatch, fault):
    request, calls, remote, image = transport
    initial_request, initial_image, initial_run = request, copy.deepcopy(image), mod.run
    cancel = Event()
    if fault == "id":
        image["Id"] = "sha256:" + "c" * 64
    if fault == "platform":
        image["Architecture"] = "arm64"
    if fault == "label":
        image["Config"]["Labels"][mod.LABEL] = "c" * 64
    if fault == "user":
        image["Config"]["User"] = "0"
    if fault == "index":
        image["Descriptor"] = {"mediaType": "index"}
    if fault == "absent":
        request = request.model_copy(
            update={"docker": request.docker.model_copy(update={"socket": "/absent"})}
        )
    if fault == "auth":
        remote[DESTINATION] = BuildError("authentication_denied")
    if fault.startswith("remote-"):
        value = copy.deepcopy(REMOTE)
        if fault == "remote-config":
            value["OCIManifest"]["config"]["digest"] = "sha256:" + "c" * 64
        if fault == "remote-platform":
            value["Descriptor"]["platform"]["architecture"] = "arm64"
        if fault == "remote-index":
            value = [value]
        if fault == "remote-raw":
            value["Raw"] = "bad"
        if fault == "remote-json":
            value = {}
        remote[DESTINATION] = value
    if fault == "cancel":
        cancel.set()
    if fault in {"post-upload", "verify"}:
        original = mod.run

        def changed(req, work, args, deadline, cancel=None, **kwargs):
            result = original(req, work, args, deadline, cancel, **kwargs)
            if (fault == "post-upload" and args[:2] == ["image", "push"]) or (
                fault == "verify" and args[:3] == ["buildx", "imagetools", "create"]
            ):
                raise BuildError("network_failure")
            return result

        monkeypatch.setattr(mod, "run", changed)
    with pytest.raises(
        BuildError,
        match={
            "id": "local_image_unverified",
            "platform": "local_image_unverified",
            "label": "local_image_unverified",
            "user": "local_image_unverified",
            "index": "single_manifest_required",
            "absent": "oci_push_refused",
            "auth": "authentication_denied",
            "remote-config": "remote_manifest_unverified",
            "remote-platform": "remote_image_conflict",
            "remote-index": "remote_manifest_unverified",
            "remote-raw": "oci_push_refused",
            "remote-json": "oci_push_refused",
            "post-upload": "remote_state_unconfirmed",
            "verify": "remote_state_unconfirmed",
            "cancel": "cancelled",
        }[fault],
    ) as error:
        push(request, workspace=tmp_path, cancel=cancel)
    assert SECRET not in str(error.value)
    assert not list(tmp_path.glob("oci-push-*"))
    if fault not in {"post-upload", "verify"}:
        assert not any(c[:2] == ["image", "push"] for c in calls)
    image.clear()
    image.update(initial_image)
    remote.clear()
    cancel.clear()
    monkeypatch.setattr(mod, "run", initial_run)
    assert push(initial_request, workspace=tmp_path, cancel=cancel).published


@pytest.mark.parametrize(
    "value",
    [
        [],
        {},
        {"credsStore": "evil"},
        {"auths": {}},
        {"auths": {REGISTRY: {"identitytoken": "secret"}}},
        {"auths": {REGISTRY: {"auth": 3}}},
        {"auths": {REGISTRY: {"auth": "bad"}}},
        {"auths": {REGISTRY: {"auth": "YWJj"}}},
    ],
)
def test_authentication_refusals(request_data, tmp_path, value):
    Path(request_data["authentication"]["config_file"]).write_text(json.dumps(value))
    with pytest.raises((BuildError, ValueError)):
        authentication(PushRequest.model_validate(request_data), tmp_path)


def test_explicit_auth_and_ca_private_copy(request_data, tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_bytes(b"test certificate")
    request_data["authentication"]["ca_file"] = str(ca)
    authentication(PushRequest.model_validate(request_data), tmp_path)
    assert (tmp_path / "docker-config/config.json").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "registry-ca.pem").read_bytes() == ca.read_bytes()


@pytest.mark.timeout(10)
@pytest.mark.parametrize(
    "diagnostic,absent",
    [
        ("no such manifest: " + DESTINATION, True),
        ("unauthorized", False),
        ("x509: unknown authority", False),
        ("connection refused", False),
        ("manifest unknown", False),
        ("no such manifest: other", False),
    ],
)
def test_only_exact_docker_absence_is_accepted(
    request_data, tmp_path, diagnostic, absent
):
    request = PushRequest.model_validate(request_data)
    script = "import sys;sys.stderr.write(" + repr(diagnostic + "\n") + ");sys.exit(1)"
    if absent:
        assert (
            run(
                request,
                tmp_path,
                ["-c", script],
                time.monotonic() + 2,
                absent_reference=DESTINATION,
            )
            == b"null"
        )
    else:
        with pytest.raises(BuildError, match="docker_command_failed"):
            run(
                request,
                tmp_path,
                ["-c", script],
                time.monotonic() + 2,
                absent_reference=DESTINATION,
            )
    assert (
        run(request, tmp_path, ["-c", "print('ok')"], time.monotonic() + 2) == b"ok\n"
    )


@pytest.mark.parametrize(
    "config",
    [
        {"IndexConfigs": {REGISTRY: {"Secure": False}}, "InsecureRegistryCIDRs": []},
        {"IndexConfigs": {}, "InsecureRegistryCIDRs": ["0.0.0.0/0"]},
    ],
)
def test_insecure_daemon_refused(transport, tmp_path, monkeypatch, config):
    request, calls, remote, image = transport
    original = mod.run

    def changed(req, work, args, deadline, cancel=None, **kwargs):
        if args[0] == "info":
            return json.dumps(config).encode()
        return original(req, work, args, deadline, cancel, **kwargs)

    monkeypatch.setattr(mod, "run", changed)
    with pytest.raises(BuildError, match="insecure_registry_configuration"):
        push(request, workspace=tmp_path)
    assert not any(c[:2] == ["image", "push"] for c in calls)


@pytest.mark.parametrize(
    "fault", [None, "remote_state_unconfirmed", "oci_push_refused"]
)
def test_push_protocol(transport, tmp_path, monkeypatch, capsys, fault):
    import io
    from types import SimpleNamespace

    from apizr_oci import protocol

    request, calls, remote, image = transport
    monkeypatch.chdir(tmp_path)
    payload = {
        "protocol": "apizr.extension/v1",
        "request_id": "a" * 32,
        "operation": "push",
        "arguments": request.model_dump(by_alias=True),
    }
    monkeypatch.setattr(
        sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode()))
    )
    if fault:

        def failed(*args, **kwargs):
            raise BuildError(fault)

        monkeypatch.setattr(protocol, "push", failed)
    assert protocol.main() == 0
    output = capsys.readouterr()
    reply = json.loads(output.out)
    assert reply["request_id"] == payload["request_id"] and reply["operation"] == "push"
    assert SECRET not in output.out + output.err
    if fault:
        assert reply["status"] == "error"
        assert reply["error"]["code"] == (
            "remote_state_unconfirmed"
            if fault == "remote_state_unconfirmed"
            else "oci_push_failed"
        )
    else:
        assert reply["result"]["published"] is True


def test_explicit_ca_environment_without_parent_credentials(
    request_data, tmp_path, monkeypatch
):
    request_data["authentication"]["ca_file"] = str(tmp_path / "source.pem")
    request = PushRequest.model_validate(request_data)
    monkeypatch.setenv("DOCKER_AUTH_CONFIG", SECRET)
    monkeypatch.setenv("SSL_CERT_FILE", "unselected")
    code = "import os; assert 'DOCKER_AUTH_CONFIG' not in os.environ; print(os.environ['SSL_CERT_FILE'])"
    assert run(
        request, tmp_path, ["-c", code], time.monotonic() + 2
    ).decode().strip() == str(tmp_path / "registry-ca.pem")


@pytest.mark.parametrize("registry", ["docker.io", "index.docker.io"])
def test_selected_hub_credentials_use_docker_canonical_key(
    request_data, tmp_path, registry
):
    config = Path(request_data["authentication"]["config_file"])
    selected = json.loads(config.read_text())["auths"][REGISTRY]
    config.write_text(json.dumps({"auths": {registry: selected}}))
    request_data["destination"] = registry + "/services/rest:v1"
    authentication(PushRequest.model_validate(request_data), tmp_path)
    copied = json.loads((tmp_path / "docker-config/config.json").read_text())
    assert copied == {"auths": {"https://index.docker.io/v1/": selected}}
    assert json.loads(config.read_text()) == {"auths": {registry: selected}}


@pytest.mark.parametrize(
    "reference,expected",
    [
        ("index.docker.io/services/rest:v1", "docker.io/services/rest:v1"),
        (
            "index.docker.io.evil.test/services/rest:v1",
            "index.docker.io.evil.test/services/rest:v1",
        ),
        (
            "registry.test/services/index.docker.io/rest:v1",
            "registry.test/services/index.docker.io/rest:v1",
        ),
    ],
)
def test_hub_alias_absence_uses_docker_normalized_reference(
    request_data, tmp_path, monkeypatch, reference, expected
):
    calls = []

    def inspect(req, work, args, deadline, cancel=None, **kwargs):
        calls.append((args[-1], kwargs["absent_reference"]))
        return b"null"

    monkeypatch.setattr(mod, "run", inspect)
    assert (
        mod.remote_identity(
            PushRequest.model_validate(request_data),
            tmp_path,
            reference,
            time.monotonic() + 1,
            None,
            absent=True,
        )
        is None
    )
    assert calls == [(expected, expected)]

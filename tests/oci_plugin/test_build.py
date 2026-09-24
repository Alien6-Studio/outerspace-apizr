"""Static admission and real bounded client processes; Docker proof runs in CI."""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

import pytest
from apizr_oci.build import build, dockerfile
from apizr_oci.model import BuildError, BuildRequest
from apizr_oci.process import run
from apizr_oci.snapshot import bundle_snapshot, input_digest, read, wheels_snapshot
from pydantic import ValidationError

from apizr.local_plugins.models import PluginError


def arguments(tmp_path):
    return {
        "schema": "apizr.oci-build/v1",
        "bundle": str(tmp_path / "bundle"),
        "interface": "rest",
        "base_image": "python@sha256:" + "a" * 64,
        "platform": "linux/amd64",
        "tag": "apizr-test:local",
        "requirements": str(tmp_path / "requirements.lock"),
        "wheelhouse": str(tmp_path / "wheels"),
        "docker": {"executable": sys.executable, "socket": str(tmp_path / "socket")},
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "v2"),
        ("interface", "shell"),
        ("platform", "windows/amd64"),
        ("base_image", "python:latest"),
        ("base_image", "python\nRUN echo bad@sha256:" + "a" * 64),
        ("tag", "--help"),
        ("bundle", "relative"),
        ("bundle", "/tmp/a\n"),
        ("timeout_ms", 540001),
        ("timeout_ms", True),
        ("max_log_bytes", 0),
        ("command", "echo bad"),
    ],
)
def test_invalid_inputs(tmp_path, field, value):
    with pytest.raises(ValidationError):
        BuildRequest.model_validate(arguments(tmp_path) | {field: value})


def test_static_snapshot_ignores_foreign_files(bundle, tmp_path):
    # Existing fixture contains an unrelated module that raises if imported.
    (bundle / "Dockerfile").write_text("RUN touch /must-not-execute")
    (bundle / ".env").write_text("secret")
    (bundle / ".git").mkdir()
    (bundle / ".ssh").mkdir()
    os.mkfifo(bundle / "foreign-socket")
    target = tmp_path / "copy"
    bundle_snapshot(bundle, target, "rest")
    assert not any(
        (target / p).exists()
        for p in ["Dockerfile", ".env", ".git", ".ssh", "foreign-socket"]
    )
    assert (
        (target / "source/shop/admin.py").read_bytes().startswith(b"raise RuntimeError")
    )
    before = input_digest(target)
    (bundle / "source/shop/api.py").write_text("raise RuntimeError('changed')")
    assert input_digest(target) == before


@pytest.mark.parametrize(
    "alter",
    ["modified", "symlink", "fifo", "governed", "foreign", "traversal", "duplicate"],
)
def test_bundle_refusals(bundle, tmp_path, alter):
    manifest = bundle / "apizr-repository-rest.json"
    doc = json.loads(manifest.read_text())
    source = bundle / "source/shop/api.py"
    if alter == "modified":
        source.write_text("changed")
    elif alter in {"symlink", "fifo"}:
        source.unlink()
        if alter == "symlink":
            source.symlink_to(tmp_path / "outside")
        else:
            os.mkfifo(source)
    elif alter == "governed":
        doc["schema_version"] = "apizr.governed-repository-rest/v1"
        manifest.write_text(json.dumps(doc))
    elif alter in {"foreign", "traversal"}:
        doc["artifacts"][".env" if alter == "foreign" else "../outside"] = {
            "algorithm": "sha256",
            "value": "a" * 64,
        }
        manifest.write_text(json.dumps(doc))
    else:
        manifest.write_text('{"schema_version":"x","schema_version":"y"}')
    with pytest.raises((BuildError, ValueError, OSError)):
        bundle_snapshot(bundle, tmp_path / "copy", "rest")


@pytest.mark.parametrize("name", ["../x", "/x", "a/../x", "a\\b", "a//b", ""])
def test_path_refused(tmp_path, name):
    with pytest.raises(BuildError):
        read(tmp_path, name, 10)


def test_bounded_read_and_symlink_parent(tmp_path):
    (tmp_path / "large").write_bytes(b"1234")
    with pytest.raises(BuildError, match="input_size"):
        read(tmp_path, "large", 3)
    (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        read(tmp_path, "link/large", 10)


@pytest.mark.parametrize(
    "fault", [None, "missing", "hash", "pth", "extra", "metadata", "symlink"]
)
def test_verified_wheels(tmp_path, wheel_factory, fault):
    files = {"evil.pth": b"import os"} if fault == "pth" else {}
    wheel, digest = wheel_factory(plugin=False, files=files)
    house = tmp_path / "wheels"
    house.mkdir()
    copy = house / wheel.name
    if fault == "symlink":
        copy.symlink_to(wheel)
    elif fault != "missing":
        shutil.copyfile(wheel, copy)
    lock = tmp_path / "lock"
    lock.write_text(
        f"local-probe=={'2.0' if fault == 'metadata' else '1.0'} --hash=sha256:{'0' * 64 if fault == 'hash' else digest}\n"
    )
    if fault == "extra":
        (house / "extra.txt").write_text("unlocked")
    target = tmp_path / "copy"
    target.mkdir()
    if fault:
        with pytest.raises((BuildError, PluginError, OSError)):
            wheels_snapshot(lock, house, target)
    else:
        wheels_snapshot(lock, house, target)
        wheel.write_bytes(b"changed after validation")
        assert (
            hashlib.sha256((target / "wheels" / wheel.name).read_bytes()).hexdigest()
            == digest
        )


def test_dockerfile_fixed_entrypoint(tmp_path):
    for interface in ("rest", "mcp"):
        req = BuildRequest.model_validate(
            arguments(tmp_path) | {"interface": interface}
        )
        text = dockerfile(req)
        assert "USER 65532:65532" in text and "--require-hashes" in text
        assert "--no-index" in text and "--only-binary=:all:" in text
        assert "load_bundle" not in text and "docker.sock" not in text
        assert ('"0.0.0.0"' if interface == "rest" else '"server.py"') in text


@pytest.mark.timeout(10)
@pytest.mark.parametrize(
    "fault", ["success", "failure", "stdout", "stderr", "timeout", "cancel"]
)
def test_real_client_limits_and_recovery(tmp_path, fault, monkeypatch):
    req = BuildRequest.model_validate(arguments(tmp_path) | {"max_log_bytes": 1024})
    monkeypatch.setenv("SECRET_SENTINEL", "not-in-child")
    cancel = Event()
    code = "import os; assert 'SECRET_SENTINEL' not in os.environ; print('ok')"
    if fault == "failure":
        code = "raise SystemExit(42)"
    if fault in {"stdout", "stderr"}:
        code = f"import os\nwhile True: os.write({1 if fault == 'stdout' else 2},b'x'*4096)"
    if fault in {"timeout", "cancel"}:
        code = "import time; time.sleep(20)"
    processes = []
    popen = subprocess.Popen

    def capture(*args, **kwargs):
        p = popen(*args, **kwargs)
        processes.append(p)
        return p

    monkeypatch.setattr(subprocess, "Popen", capture)
    if fault == "cancel":
        cancel.set()
    if fault == "success":
        assert run(req, tmp_path, ["-c", code], time.monotonic() + 2, cancel) == b"ok\n"
    else:
        with pytest.raises(BuildError):
            run(
                req,
                tmp_path,
                ["-c", code],
                time.monotonic() + (0.1 if fault == "timeout" else 2),
                cancel,
            )
    for p in processes:
        assert p.poll() is not None and p.stdout.closed and p.stderr.closed
    assert run(req, tmp_path, ["-c", "print('ok')"], time.monotonic() + 2) == b"ok\n"


def test_docker_absent(tmp_path):
    with pytest.raises(BuildError, match="docker_unavailable"):
        build(BuildRequest.model_validate(arguments(tmp_path)), workspace=tmp_path)
    assert not list(tmp_path.glob("oci-build-*"))


def test_invalid_bundle_cleanup(bundle, tmp_path):
    with (
        TemporaryDirectory(prefix="az-oci-") as directory,
        socket.socket(socket.AF_UNIX) as sock,
    ):
        raw = arguments(tmp_path)
        raw["docker"]["socket"] = directory + "/sock"
        request = BuildRequest.model_validate(raw)
        sock.bind(request.docker.socket)
        (bundle / "source/shop/api.py").write_bytes(b"tampered")
        with pytest.raises(BuildError, match="invalid_build_inputs"):
            build(request, workspace=tmp_path)
    assert not list(tmp_path.glob("oci-build-*"))


@pytest.fixture
def build_inputs(bundle, tmp_path, wheel_factory):
    wheel, digest = wheel_factory(plugin=False)
    house = tmp_path / "wheels"
    house.mkdir()
    shutil.copyfile(wheel, house / wheel.name)
    (tmp_path / "requirements.lock").write_text(
        f"local-probe==1.0 --hash=sha256:{digest}\n"
    )
    fake = tmp_path / "docker"
    fake.write_text(
        f"#!{sys.executable}\n"
        + """import json,os,sys
from pathlib import Path
assert 'SECRET_SENTINEL' not in os.environ
assert 'DOCKER_AUTH_CONFIG' not in os.environ
args=sys.argv[1:]
if args[0]=='build':
 assert '--network=none' in args
 context=Path(args[-1])
 assert (context/'bundle/repository-interface.json').is_file()
 assert not (context/'bundle/.env').exists()
 digest=args[args.index('--label')+1].split('=',1)[1]
 Path('state').write_text(digest)
 Path(args[args.index('--iidfile')+1]).write_text('sha256:'+'b'*64)
 Path(args[args.index('--metadata-file')+1]).write_text(json.dumps({'containerimage.config.digest':'sha256:'+'b'*64,'containerimage.digest':'sha256:'+'c'*64}))
else:
 print(json.dumps([{'Id':'sha256:'+'b'*64,'Os':'linux','Architecture':'amd64','Config':{'User':'65532:65532','Labels':{'sh.outerspace.apizr.inputs-sha256':Path('state').read_text()}}}]))
"""
    )
    fake.chmod(0o700)
    with (
        TemporaryDirectory(prefix="az-oci-") as directory,
        socket.socket(socket.AF_UNIX) as sock,
    ):
        path = directory + "/sock"
        sock.bind(path)
        yield BuildRequest.model_validate(
            arguments(tmp_path) | {"docker": {"executable": str(fake), "socket": path}}
        )


def test_success_verified_cleanup_and_determinism(build_inputs, tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_SENTINEL", "secret")
    monkeypatch.setenv("DOCKER_AUTH_CONFIG", "secret")
    result = build(build_inputs, workspace=tmp_path)
    assert result.image_id == "sha256:" + "b" * 64
    assert result.published is False and len(result.inputs_sha256) == 64
    assert not list(tmp_path.glob("oci-build-*"))
    assert build(build_inputs, workspace=tmp_path) == result


@pytest.mark.parametrize(
    "fault",
    [
        "id",
        "os",
        "user",
        "label",
        "malformed",
        "no-iid",
        "mismatch",
        "missing-wheel",
        "requirements",
        "timeout",
        "cancel",
    ],
)
def test_build_failures_cleanup_and_recover(build_inputs, tmp_path, fault):
    fake = Path(build_inputs.docker.executable)
    original = fake.read_text()
    cancel = Event()
    request = build_inputs
    if fault in {"id", "os", "user", "label"}:
        changes = {
            "id": ("'Id':'sha256:'+'b'*64", "'Id':'invalid'"),
            "os": ("'Os':'linux'", "'Os':'other'"),
            "user": ("'User':'65532:65532'", "'User':'0'"),
            "label": ("Path('state').read_text()", "'wrong'"),
        }
        fake.write_text(original.replace(*changes[fault]))
    elif fault == "malformed":
        fake.write_text(f'#!{sys.executable}\nprint("bad json")\n')
    elif fault == "no-iid":
        fake.write_text(f"#!{sys.executable}\n")
    elif fault == "mismatch":
        lock = Path(request.requirements)
        saved = lock.read_text()
        lock.write_text(saved.replace("1.0", "2.0"))
    elif fault == "missing-wheel":
        wheel = next(Path(request.wheelhouse).glob("*.whl"))
        wheel.rename(wheel.with_suffix(".other"))
    elif fault == "requirements":
        manifest = Path(request.bundle) / "apizr-repository-rest.json"
        saved_manifest = manifest.read_bytes()
        requirements = Path(request.bundle) / "requirements.txt"
        saved_requirements = requirements.read_bytes()
        requirements.write_bytes(b"https://forbidden.invalid/file.whl\n")
        document = json.loads(saved_manifest)
        document["artifacts"]["requirements.txt"]["value"] = hashlib.sha256(
            requirements.read_bytes()
        ).hexdigest()
        manifest.write_text(json.dumps(document))
    elif fault == "timeout":
        request = request.model_copy(update={"timeout_ms": 1})
    elif fault == "cancel":
        cancel.set()
    try:
        with pytest.raises(BuildError):
            build(request, workspace=tmp_path, cancel=cancel)
        assert not list(tmp_path.glob("oci-build-*"))
    finally:
        fake.write_text(original)
        if fault == "mismatch":
            lock.write_text(saved)
        if fault == "missing-wheel":
            wheel.with_suffix(".other").rename(wheel)
        if fault == "requirements":
            manifest.write_bytes(saved_manifest)
            requirements.write_bytes(saved_requirements)
    assert build(build_inputs, workspace=tmp_path).published is False


def test_cli_timeout_default_override_and_bounds(monkeypatch, capsys, tmp_path):
    from types import SimpleNamespace

    import apizr.plugins_cli as cli

    captured = []
    monkeypatch.setattr(cli, "read_arguments", lambda *a, **k: {})

    def invoke(*args, **kwargs):
        captured.append(kwargs["limits"].wall_time_ms)
        return SimpleNamespace(model_dump_json=lambda: "{}")

    monkeypatch.setattr(cli, "run_extension", invoke)
    args = ["run", "apizr-oci", "build", "--arguments", str(tmp_path / "build.json")]
    assert cli.main(args) == 0
    assert cli.main(args + ["--timeout-ms", "360000"]) == 0
    assert captured == [10000, 360000]
    for invalid in ("0", "600001", "nan", "secret"):
        with pytest.raises(SystemExit) as failure:
            cli.main(args + ["--timeout-ms", invalid])
        assert failure.value.code == 2


@pytest.mark.parametrize(
    "payload",
    [b"not json", b"{}", b"x" * 1048577],
    ids=["invalid-json", "invalid-object", "oversized"],
)
def test_protocol_invalid_request_is_redacted(payload):
    env = dict(
        os.environ, PYTHONPATH=str(Path(__file__).parents[2] / "plugins/oci/src")
    )
    result = subprocess.run(
        [sys.executable, "-m", "apizr_oci.protocol"],
        input=payload,
        capture_output=True,
        env=env,
        timeout=5,
    )
    assert result.returncode == 2 and result.stdout == b""
    assert result.stderr == b"invalid_extension_request\n"


@pytest.mark.parametrize(
    "operation,args", [("unknown", {}), ("build", {}), ("build", {"schema": "secret"})]
)
def test_protocol_operation_errors(operation, args):
    env = dict(
        os.environ, PYTHONPATH=str(Path(__file__).parents[2] / "plugins/oci/src")
    )
    request = {
        "protocol": "apizr.extension/v1",
        "request_id": "a" * 32,
        "operation": operation,
        "arguments": args,
    }
    result = subprocess.run(
        [sys.executable, "-m", "apizr_oci.protocol"],
        input=json.dumps(request).encode(),
        capture_output=True,
        env=env,
        timeout=5,
    )
    response = json.loads(result.stdout)
    assert (
        response["request_id"] == request["request_id"]
        and response["status"] == "error"
    )
    assert b"secret" not in result.stdout and result.stderr == b""


@pytest.mark.parametrize(
    "case", ["success", "operation", "arguments", "json", "oversized"]
)
def test_protocol_in_process(build_inputs, tmp_path, monkeypatch, capsys, case):
    import io
    from types import SimpleNamespace

    from apizr_oci.protocol import main

    request = {
        "protocol": "apizr.extension/v1",
        "request_id": "a" * 32,
        "operation": "build",
        "arguments": build_inputs.model_dump(by_alias=True),
    }
    if case == "operation":
        request["operation"] = "unknown"
    if case == "arguments":
        request["arguments"] = {}
    raw = json.dumps(request).encode()
    if case == "json":
        raw = b"invalid"
    if case == "oversized":
        raw = b"x" * 1048577
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))
    monkeypatch.chdir(tmp_path)
    code = main()
    out, err = capsys.readouterr()
    if case in {"json", "oversized"}:
        assert code == 2 and out == "" and err == "invalid_extension_request\n"
    else:
        assert code == 0 and err == ""
        response = json.loads(out)
        assert response["request_id"] == "a" * 32
        assert response["status"] == ("ok" if case == "success" else "error")


def test_buildx_explicit_and_missing(tmp_path):
    raw = arguments(tmp_path)
    raw["docker"]["buildx"] = sys.executable
    req = BuildRequest.model_validate(raw)
    assert run(req, tmp_path, ["-c", "print('ok')"], time.monotonic() + 2) == b"ok\n"
    assert (tmp_path / "docker-config/cli-plugins/docker-buildx").is_symlink()
    assert run(req, tmp_path, ["-c", "print('ok')"], time.monotonic() + 2) == b"ok\n"
    raw["docker"]["buildx"] = "/missing/buildx"
    with pytest.raises(BuildError, match="buildx_unavailable"):
        run(BuildRequest.model_validate(raw), tmp_path, [], time.monotonic() + 2)
    raw["docker"]["buildx"] = "relative"
    with pytest.raises(ValueError):
        BuildRequest.model_validate(raw)


def test_spawn_failure_and_cancel_after_spawn(tmp_path, monkeypatch):
    raw = arguments(tmp_path)
    raw["docker"]["executable"] = "/missing/docker"
    with pytest.raises(BuildError, match="docker_unavailable"):
        run(BuildRequest.model_validate(raw), tmp_path, [], time.monotonic() + 1)
    req = BuildRequest.model_validate(arguments(tmp_path))
    with pytest.raises(BuildError, match="timeout"):
        run(req, tmp_path, [], time.monotonic() - 1)
    cancel = Event()
    original = subprocess.Popen

    def spawn(*args, **kwargs):
        child = original(*args, **kwargs)
        cancel.set()
        return child

    monkeypatch.setattr(subprocess, "Popen", spawn)
    with pytest.raises(BuildError, match="cancelled"):
        run(
            req,
            tmp_path,
            ["-c", "import time; time.sleep(60)"],
            time.monotonic() + 3,
            cancel,
        )


def test_containerd_image_identity(build_inputs, tmp_path):
    fake = Path(build_inputs.docker.executable)
    fake.write_text(
        fake.read_text().replace("'Id':'sha256:'+'b'*64", "'Id':'sha256:'+'c'*64")
    )
    assert build(build_inputs, workspace=tmp_path).image_id == "sha256:" + "c" * 64


def test_wheelhouse_global_bounds(tmp_path, wheel_factory, monkeypatch):
    import apizr_oci.snapshot as snapshot

    wheel, digest = wheel_factory(plugin=False)
    house = tmp_path / "wheels"
    house.mkdir()
    shutil.copyfile(wheel, house / wheel.name)
    lock = tmp_path / "requirements.lock"
    lock.write_text(f"local-probe==1.0 --hash=sha256:{digest}\n")
    for limit, value in [("MAX_WHEELS", 0), ("MAX_TOTAL_EXPANDED_BYTES", 1)]:
        target = tmp_path / limit
        target.mkdir()
        with monkeypatch.context() as patch:
            patch.setattr(snapshot, limit, value)
            with pytest.raises(BuildError):
                wheels_snapshot(lock, house, target)
    target = tmp_path / "missing"
    target.mkdir()
    (house / wheel.name).unlink()
    with pytest.raises(BuildError, match="missing_locked_wheel"):
        wheels_snapshot(lock, house, target)

"""Real isolated updates and explicitly synchronized activation races."""

import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from apizr.cli import main
from apizr.extension_runtime import Limits
from apizr.local_plugins import (
    activation,
    backend,
    disable_extension,
    enable_extension,
    install_extension,
    list_extensions,
    run_extension,
    store,
)
from apizr.local_plugins.control import InstallationCancelled
from apizr.local_plugins.models import PluginError
from apizr.plugin_lock import create_lock
from apizr.plugin_update import operations, update_plugin

pytestmark = pytest.mark.timeout(30)

PROGRAM = b"""import json,sys,time
from pathlib import Path
from update_helper import VALUE
r=json.load(sys.stdin)
a=r['arguments']
if 'ready' in a:
 Path(a['ready']).write_text('ready')
 end=time.monotonic()+10
 while not Path(a['release']).exists():
  if time.monotonic()>end: raise SystemExit(2)
  time.sleep(0.01)
print(json.dumps({k:r[k] for k in ('protocol','request_id','operation')}|{'status':'ok','result':VALUE}))
"""


@pytest.fixture
def setup(wheel_factory, tmp_path):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    projects = {}
    for number in (1, 2, 3):
        version = f"{number}.0"
        leaf, digest = wheel_factory(
            name="update-leaf",
            version=version,
            plugin=False,
            files={"update_leaf.py": f"VALUE = {number * 10}\n".encode()},
        )
        leaf.rename(wheels / leaf.name)
        lines = [f"update-leaf=={version} --hash=sha256:{digest}\n"]
        helper, digest = wheel_factory(
            name="update-helper",
            version=version,
            plugin=False,
            metadata_extra=f"Requires-Dist: update-leaf=={version}\n",
            files={"update_helper.py": b"from update_leaf import VALUE\n"},
        )
        helper.rename(wheels / helper.name)
        lines.append(f"update-helper=={version} --hash=sha256:{digest}\n")
        wheel, digest = wheel_factory(
            name="update-probe",
            version=version,
            metadata_extra=f"Requires-Dist: update-helper=={version}\n",
            files={"local_probe.py": PROGRAM},
        )
        wheel.rename(wheels / wheel.name)
        lines.append(f"update-probe=={version} --hash=sha256:{digest}\n")
        folder = tmp_path / version
        folder.mkdir()
        (folder / "requirements.lock").write_text("".join(lines))
        path = folder / "apizr.toml"
        path.write_text(
            f'schema_version = "apizr.project/v1"\n[[plugins]]\nname="update-probe"\nversion="{version}"\nsha256="{digest}"\nrequirements="requirements.lock"\n'
        )
        lock = folder / "next.lock.json"
        assert create_lock(path, wheels, lock).valid
        projects[version] = (path, lock, wheels)
    root = tmp_path / "store"
    # Offer only the source's own exact closure, as the local installer requires.
    closure = tmp_path / "source-wheels"
    closure.mkdir()
    import shutil

    for wheel in wheels.glob("*-1.0-*.whl"):
        shutil.copyfile(wheel, closure / wheel.name)
    source = install_extension(
        closure / "update_probe-1.0-py3-none-any.whl",
        json.loads(projects["1.0"][1].read_text())["plugins"][0]["wheel"]["sha256"],
        requirements=projects["1.0"][0].parent / "requirements.lock",
        wheelhouse=closure,
        directory=root,
    )
    enable_extension("update-probe", "1.0", directory=root)
    assert run_extension("update-probe", "answer", {}, directory=root).result == 10
    return projects, root, source


def update(setup, version="2.0", **kwargs):
    projects, root, _ = setup
    return update_plugin(
        "update-probe", "1.0", *projects[version], directory=root, **kwargs
    )


def snapshot(root):
    return {
        str(p.relative_to(root)): ("link", os.readlink(p))
        if p.is_symlink()
        else ("file", p.read_bytes())
        for p in root.rglob("*")
        if p.is_file() or p.is_symlink()
    }


def active(root):
    return activation.resolve_active_extension("update-probe", directory=root)


def test_prepare_transition_idempotence_and_explicit_rollback(setup, monkeypatch):
    projects, root, source = setup
    old = root / "environments" / source.environment_id
    before = snapshot(old)
    result = update(setup)
    assert result.state == "complete" and result.installation == "installed"
    assert result.activation == "not_requested" and active(root) == source
    assert run_extension("update-probe", "answer", {}, directory=root).result == 10
    with monkeypatch.context() as c:
        c.setenv("PATH", "")
        result = update(setup, activate=True)
        assert (
            result.exit_code == 0
            and result.activation == "changed"
            and result.installation == "reused"
        )
        assert update(setup, activate=True).activation == "unchanged"
    assert run_extension("update-probe", "answer", {}, directory=root).result == 20
    enable_extension("update-probe", "1.0", directory=root)
    assert run_extension("update-probe", "answer", {}, directory=root).result == 10
    assert snapshot(old) == before
    assert len(list_extensions(directory=root).installations) == 2


def test_dry_run_no_process_mutation_and_same_target(setup, monkeypatch):
    _, root, _ = setup
    before = snapshot(root)

    def forbidden(*a, **k):
        raise AssertionError("dry-run process")

    with monkeypatch.context() as c:
        c.setattr(subprocess, "Popen", forbidden)
        c.setattr(backend, "require_uv", forbidden)
        result = update(setup, activate=True, dry_run=True)
        assert result.state == "planned" and result.activation == "planned"
        assert not result.interpreter_verified
    assert snapshot(root) == before
    result = update(setup, "1.0", activate=True)
    assert (
        result.exit_code == 0
        and result.installation == "reused"
        and result.activation == "unchanged"
    )
    assert snapshot(root) == before


@pytest.mark.parametrize(
    "case", ["source", "name", "inactive", "third", "conflict", "target", "artifact"]
)
def test_preflight_refusals_preserve_state(setup, wheel_factory, case):
    projects, root, _ = setup
    args = ("update-probe", "1.0", *projects["2.0"])
    if case == "source":
        args = ("update-probe", "9.0", *projects["2.0"])
    if case == "name":
        args = ("unknown", "1.0", *projects["2.0"])
    if case == "inactive":
        disable_extension("update-probe", directory=root)
    if case == "third":
        assert update(setup, "3.0").exit_code == 0
        enable_extension("update-probe", "3.0", directory=root)
    if case == "conflict":
        wheel, digest = wheel_factory(name="update-probe", version="2.0")
        install_extension(wheel, digest, directory=root)
    if case == "target":
        doc = json.loads(projects["2.0"][1].read_text())
        doc["target"]["python"] = "3.99.0"
        projects["2.0"][1].write_text(json.dumps(doc))
    if case == "artifact":
        (projects["2.0"][2] / "update_probe-2.0-py3-none-any.whl").write_bytes(b"bad")
    before = snapshot(root)
    result = update_plugin(*args, directory=root, activate=True)
    assert result.exit_code == 1 and result.state == "refused"
    assert snapshot(root) == before


def test_only_named_plugin_and_foreign_activation_untouched(setup, wheel_factory):
    projects, root, source = setup
    wheel, digest = wheel_factory(name="foreign")
    other = install_extension(wheel, digest, directory=root)
    enable_extension("foreign", "1.0", directory=root)
    extra, extra_hash = wheel_factory(name="uninstalled")
    extra.rename(projects["2.0"][2] / extra.name)
    path, lock, wheels = projects["2.0"]
    path.write_text(
        path.read_text()
        + f'\n[[plugins]]\nname="uninstalled"\nversion="1.0"\nsha256="{extra_hash}"\n'
    )
    new = lock.with_name("with-extra.lock.json")
    assert create_lock(path, wheels, new).valid
    assert (
        update_plugin(
            "update-probe", "1.0", path, new, wheels, directory=root
        ).exit_code
        == 0
    )
    inventory = list_extensions(directory=root)
    assert source in inventory.installations and other in inventory.installations
    assert {r.name for r in inventory.installations} == {"update-probe", "foreign"}
    assert activation.resolve_active_extension("foreign", directory=root) == other


def test_original_inputs_replaced_after_preparation(setup, monkeypatch):
    projects, root, _ = setup
    original = operations.installation_state
    replaced = False

    def read(*args):
        nonlocal replaced
        if not replaced:
            replaced = True
            for p in projects["2.0"][:2]:
                p.write_bytes(b"bad")
            (projects["2.0"][0].parent / "requirements.lock").write_bytes(b"bad")
            for p in projects["2.0"][2].iterdir():
                p.write_bytes(b"bad")
        return original(*args)

    monkeypatch.setattr(operations, "installation_state", read)
    assert update(setup, activate=True).exit_code == 0
    assert run_extension("update-probe", "answer", {}, directory=root).result == 20


@pytest.mark.parametrize("case", ["missing", "target"])
def test_unusable_target_is_not_activated(setup, monkeypatch, case):
    from apizr.plugin_sync import probe

    assert update(setup).exit_code == 0
    _, root, source = setup
    record = list_extensions(directory=root).installations[-1]
    if case == "missing":
        from pathlib import Path

        Path(record.python).unlink()
    else:
        monkeypatch.setattr(
            probe,
            "PROGRAM",
            probe.PROGRAM.replace("platform.python_version()", '"3.99.0"'),
        )
    result = update(setup, activate=True)
    assert result.exit_code == 2 and not result.interpreter_verified
    assert active(root) == source


@pytest.mark.parametrize("change", ["disable", "third"])
def test_activation_conflict_after_install_then_resume(setup, monkeypatch, change):
    _, root, source = setup
    assert update(setup, "3.0").exit_code == 0
    transition = activation.compare_and_activate

    def compete(*a, **k):
        if change == "disable":
            disable_extension("update-probe", directory=root)
        else:
            enable_extension("update-probe", "3.0", directory=root)
        return transition(*a, **k)

    with monkeypatch.context() as c:
        c.setattr(activation, "compare_and_activate", compete)
        result = update(setup, activate=True)
    assert (
        result.exit_code == 2
        and result.state == "partial"
        and result.installation == "installed"
    )
    assert result.activation == "refused"
    assert (
        result.active_after is None
        if change == "disable"
        else result.active_after.version == "3.0"
    )
    enable_extension(source.name, source.version, directory=root)
    retry = update(setup, activate=True)
    assert retry.exit_code == 0 and retry.installation == "reused"


@pytest.mark.parametrize("different", [False, True])
def test_concurrent_transitions_compare_complete_bindings(
    setup, monkeypatch, different
):
    barrier = threading.Barrier(2, timeout=10)
    probe = operations.verify_interpreter

    def verified(*a):
        probe(*a)
        barrier.wait()

    monkeypatch.setattr(operations, "verify_interpreter", verified)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [
            pool.submit(update, setup, v, activate=True)
            for v in ("2.0", "3.0" if different else "2.0")
        ]
        results = [t.result(timeout=15) for t in tasks]
    assert sorted(r.exit_code for r in results) == ([0, 2] if different else [0, 0])
    assert len(list_extensions(directory=setup[1]).installations) == (
        3 if different else 2
    )
    winner = next(r for r in results if r.exit_code == 0)
    assert active(setup[1]) == winner.target_installation


@pytest.mark.parametrize("after", [False, True])
def test_interruption_at_activation_reconciles_and_retries(setup, monkeypatch, after):
    _, root, source = setup
    publish = activation._publish

    def interrupt(*a):
        if after:
            publish(*a)
        raise InstallationCancelled()

    with monkeypatch.context() as c:
        c.setattr(activation, "_publish", interrupt)
        result = update(setup, activate=True)
    assert result.exit_code == 130 and result.state == "interrupted"
    assert result.installation == "installed" and result.after_known
    assert active(root) == (result.target_installation if after else source)
    assert result.activation == ("observed_target" if after else "refused")
    retry = update(setup, activate=True)
    assert retry.exit_code == 0 and retry.installation == "reused"


def test_unconfirmed_activation_keeps_all_environments(setup, monkeypatch):
    _, root, _ = setup
    publish = activation._publish

    def corrupt(*a):
        publish(*a)
        (root / "activations.json").write_bytes(b"bad")
        raise InstallationCancelled()

    monkeypatch.setattr(activation, "_publish", corrupt)
    result = update(setup, activate=True)
    assert (
        result.state == "unconfirmed"
        and result.exit_code == 130
        and not result.after_known
    )
    assert len(list_extensions(directory=root).installations) == 2
    assert len(list((root / "environments").iterdir())) == 2


def test_uv_failure_and_cancel_preserve_old_activation(setup, monkeypatch):
    _, root, source = setup
    run = backend.run_uv

    def fail(executable, args, work, **kw):
        return run(executable, [*args, "--apizr-test-invalid-option"], work, **kw)

    with monkeypatch.context() as c:
        c.setattr(backend, "run_uv", fail)
        result = update(setup, activate=True)
    assert result.exit_code == 2 and result.installation == "failed"
    assert (
        active(root) == source
        and len(list_extensions(directory=root).installations) == 1
    )
    event = threading.Event()
    event.set()
    assert update(setup, activate=True, cancel=event).exit_code == 130
    assert update(setup, activate=True).exit_code == 0


def test_lock_deadline_and_next_invocation(setup):
    assert update(setup).exit_code == 0
    with store.installation_lock(setup[1]):
        result = update(setup, activate=True, timeout_ms=50)
        assert result.exit_code == 2
    assert update(setup, activate=True).exit_code == 0


def test_inflight_old_invocation_survives_transition(setup, tmp_path):
    _, root, _ = setup
    ready, release = tmp_path / "ready", tmp_path / "release"
    cancel = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            run_extension,
            "update-probe",
            "answer",
            {"ready": str(ready), "release": str(release)},
            directory=root,
            limits=Limits(wall_time_ms=15000),
            cancel=cancel,
        )
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                cancel.wait(0.01)
            assert ready.exists()
            assert update(setup, activate=True).exit_code == 0
            release.touch()
            assert future.result(timeout=5).result == 10
            assert (
                run_extension("update-probe", "answer", {}, directory=root).result == 20
            )
        finally:
            release.touch()
            cancel.set()


def test_cli_preferences_and_partial_json(setup, tmp_path, capsys, monkeypatch):
    projects, root, _ = setup
    user = tmp_path / "user.toml"
    user.write_text('schema_version="apizr.user/v1"\nplugins_dir="wrong-store"\n')
    args = [
        "plugins",
        "update",
        "update-probe",
        "--from-version",
        "1.0",
        "--project",
        str(projects["2.0"][0]),
        "--lock",
        str(projects["2.0"][1]),
        "--wheelhouse",
        str(projects["2.0"][2]),
        "--user-config",
        str(user),
        "--plugins-dir",
        str(root),
        "--json",
        "--activate",
    ]
    assert main([*args, "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "dry-run"

    def conflict(*a, **k):
        raise PluginError("update_activation_changed")

    with monkeypatch.context() as c:
        c.setattr(activation, "compare_and_activate", conflict)
        assert main(args) == 2
        value = json.loads(capsys.readouterr().out)
        assert value["state"] == "partial" and value["installation"] == "installed"
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "complete"
    user.write_text("bad")
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["state"] == "refused"


@pytest.mark.parametrize("selection", [None, "3.0"])
def test_prepare_only_preserves_inactive_or_third_selection(setup, selection):
    _, root, _ = setup
    if selection is None:
        disable_extension("update-probe", directory=root)
    else:
        assert update(setup, selection).exit_code == 0
        enable_extension("update-probe", selection, directory=root)
    before = (root / "activations.json").read_bytes()
    result = update(setup)
    assert result.exit_code == 0 and result.activation == "not_requested"
    assert (root / "activations.json").read_bytes() == before


def test_absent_store_remains_absent(setup, tmp_path):
    projects, _, _ = setup
    root = tmp_path / "absent"
    for dry in (True, False):
        result = update_plugin(
            "update-probe", "1.0", *projects["2.0"], directory=root, dry_run=dry
        )
        assert result.exit_code == 1 and not root.exists()


@pytest.mark.parametrize("which", ["source", "target"])
def test_record_changed_before_compare_and_activate_is_refused(
    setup, monkeypatch, which
):
    _, root, _ = setup
    transition = activation.compare_and_activate

    def replace(source, target, expected, **kw):
        old = source if which == "source" else target
        replacement = old.model_copy(update={"sha256": "a" * 64})
        with store.installation_lock(root, create=False):
            inventory = store.read_inventory(root)
            state = activation._read(root)
            store.publish(
                root,
                inventory.model_copy(
                    update={
                        "installations": [
                            replacement if r == old else r
                            for r in inventory.installations
                        ]
                    }
                ),
            )
            activation._publish(
                root, [replacement if r == old else r for r in state.activations]
            )
        return transition(source, target, expected, **kw)

    monkeypatch.setattr(activation, "compare_and_activate", replace)
    result = update(setup, activate=True)
    assert result.exit_code == 2 and result.state == "partial"
    assert active(root).version == "1.0"
    assert result.diagnostics[0].code == f"update_{which}_changed"
    assert len(list_extensions(directory=root).installations) == 2


@pytest.mark.parametrize("cancelled", [False, True])
def test_real_uv_timeout_or_cancel_cleans_up_then_recovers(
    setup, tmp_path, monkeypatch, cancelled
):
    import sys

    marker = tmp_path / "uv-ready"
    executable = tmp_path / "uv-hang"
    executable.write_text(
        f"#!{sys.executable} -B\nimport os,time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n"
    )
    executable.chmod(0o700)
    event = threading.Event()
    with monkeypatch.context() as context:
        context.setattr(backend, "require_uv", lambda: str(executable))
        with ThreadPoolExecutor(max_workers=1) as pool:
            task = pool.submit(
                update,
                setup,
                activate=True,
                cancel=event,
                timeout_ms=10000 if cancelled else 1000,
            )
            limit = time.monotonic() + 3
            while not marker.exists() and time.monotonic() < limit:
                event.wait(0.01)
            assert marker.exists()
            if cancelled:
                event.set()
            result = task.result(timeout=5)
    assert result.exit_code == (130 if cancelled else 2)
    assert active(setup[1]) == setup[2]
    assert len(list_extensions(directory=setup[1]).installations) == 1
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)
    assert update(setup, activate=True).exit_code == 0


def test_update_probe_and_transition_coordinate_with_uninstall(setup, monkeypatch):
    from apizr.local_plugins import uninstall_extension
    from apizr.plugin_sync import probe

    original = probe._verify
    seen = []

    def verify(record, root, *args):
        result = uninstall_extension(record.name, record.version, directory=root)
        seen.append(result.state)
        assert result.state == "busy"
        return original(record, root, *args)

    monkeypatch.setattr(probe, "_verify", verify)
    result = update(setup, activate=True)
    assert result.state == "complete" and seen
    projects, root, source = setup
    assert (
        uninstall_extension(source.name, source.version, directory=root).state
        == "complete"
    )
    assert run_extension(source.name, "answer", {}, directory=root).result == 20


def test_update_refuses_target_retired_between_probe_and_activation(setup, monkeypatch):
    from apizr.local_plugins import uninstall_extension

    original = operations.verify_interpreter

    def verify(record, root, *args):
        original(record, root, *args)
        assert (
            uninstall_extension(record.name, record.version, directory=root).state
            == "complete"
        )

    monkeypatch.setattr(operations, "verify_interpreter", verify)
    result = update(setup, activate=True)
    assert (
        result.exit_code != 0 and result.diagnostics[0].code == "update_target_changed"
    )
    assert active(setup[1]) == setup[2]
    assert run_extension("update-probe", "answer", {}, directory=setup[1]).result == 10

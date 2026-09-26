"""Installed core: offline prepare, conditional transition, retry and explicit rollback."""

import argparse
import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
snapshot = runpy.run_path(str(REPO / "scripts/smoke_plugin_sync.py"))["snapshot"]


def prove(work: Path, core_root: Path) -> None:
    import apizr
    from apizr.local_plugins.models import Installation

    assert not Path(apizr.__file__).resolve().is_relative_to(REPO)
    assert not work.is_relative_to(REPO)
    before = snapshot(core_root)
    inventory = "import importlib.metadata,json; print(json.dumps(sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions())))"
    distributions_before = subprocess.check_output(
        [sys.executable, "-I", "-B", "-c", inventory], timeout=20
    )
    uv = shutil.which("uv")
    assert uv
    wrapper = work / "backend"
    wrapper.mkdir()
    failure = work / "fail-target"
    network = work / "backend-network.jsonl"
    (wrapper / "uv").write_text(
        f"#!{sys.executable} -B\nimport json,os,pathlib,socket,sys\n"
        "try:\n socket.create_connection(('1.1.1.1',443),timeout=0.25).close()\n"
        "except OSError:\n pass\n"
        "else:\n raise SystemExit('network isolation missing')\n"
        f"with open({str(network)!r},'a') as stream: stream.write(json.dumps({{'denied':True,'pid':os.getpid()}})+'\\n')\n"
        "args=sys.argv[1:]\n"
        f"if pathlib.Path({str(failure)!r}).exists() and '--requirements' in args:\n"
        " data=pathlib.Path(args[args.index('--requirements')+1]).read_text()\n"
        " if 'apizr-update-probe==2.0.0' in data: args.append('--apizr-test-invalid-option')\n"
        f"os.execv({uv!r},[{uv!r},*args])\n"
    )
    (wrapper / "uv").chmod(0o700)
    env = dict(
        os.environ,
        PATH=str(wrapper) + os.pathsep + os.environ.get("PATH", ""),
        PYTHONDONTWRITEBYTECODE="1",
        APIZR_TEST_SECRET="update-secret-must-not-leak",
    )
    records: list[dict] = []

    def cli(*args: str, expected: int = 0, structured: bool = True) -> dict:
        command = [sys.executable, "-I", "-B", "-m", "apizr.cli", "plugins", *args]
        result = subprocess.run(
            command, cwd=work, env=env, text=True, capture_output=True, timeout=150
        )
        assert "update-secret-must-not-leak" not in result.stdout + result.stderr
        assert result.returncode == expected, (
            result.returncode,
            result.stdout,
            result.stderr,
        )
        value = json.loads(result.stdout) if structured else {"output": result.stdout}
        records.append(
            {"arguments": list(args), "exit_code": result.returncode, "result": value}
        )
        (work / "update-evidence.json").write_text(json.dumps(records, indent=2) + "\n")
        return value

    wheels = work / "wheels"
    for version in ("1.0.0", "2.0.0"):
        folder = work / version
        cli(
            "lock",
            "create",
            "--project",
            str(folder / "apizr.toml"),
            "--wheelhouse",
            str(wheels),
            "--output",
            str(folder / "apizr.plugins.lock.json"),
            "--json",
        )
    inputs = {
        str(p): p.read_bytes()
        for p in work.rglob("*")
        if p.is_file()
        and (
            p.suffix in (".whl", ".lock", ".toml")
            or p.name == "apizr.plugins.lock.json"
        )
    }
    preference = ["--user-config", str(work / "user.toml")]

    def paths(version: str) -> list[str]:
        folder = work / version
        return [
            "--project",
            str(folder / "apizr.toml"),
            "--lock",
            str(folder / "apizr.plugins.lock.json"),
            "--wheelhouse",
            str(wheels),
            *preference,
            "--json",
        ]

    cli("sync", *paths("1.0.0"))
    cli(
        "enable",
        "apizr-update-probe",
        "--version",
        "1.0.0",
        *preference,
        structured=False,
    )

    def invoke() -> dict:
        return cli(
            "run",
            "apizr-update-probe",
            "answer",
            "--arguments",
            str(work / "arguments.json"),
            *preference,
        )

    assert invoke()["result"] == {"answer": 42}
    source = Installation.model_validate(
        json.loads((work / "plugins/installations.json").read_text())["installations"][
            0
        ]
    ).model_dump(mode="json")
    old_root = work / "plugins/environments" / source["environment_id"]
    old_distributions_before = subprocess.check_output(
        [source["python"], "-I", "-B", "-c", inventory], timeout=20
    )
    old_before = snapshot(old_root)
    store_before = snapshot(work / "plugins")
    network_before = network.read_bytes()
    command = [
        "update",
        "apizr-update-probe",
        "--from-version",
        "1.0.0",
        *paths("2.0.0"),
    ]
    preview = cli(*command, "--activate", "--dry-run")
    assert (
        preview["state"] == "planned"
        and preview["activation"] == "planned"
        and not preview["interpreter_verified"]
    )
    assert (
        snapshot(work / "plugins") == store_before
        and network.read_bytes() == network_before
    )
    failure.touch()
    failed = cli(*command, "--activate", expected=2)
    assert failed["state"] == "partial" and failed["active_after"] == source
    assert invoke()["result"] == {"answer": 42}
    failure.unlink()
    prepared = cli(*command)
    assert prepared["state"] == "complete" and prepared["installation"] == "installed"
    assert (
        prepared["activation"] == "not_requested" and prepared["active_after"] == source
    )
    assert invoke()["result"] == {"answer": 42}
    # No backend is available for the conditional switch or idempotent retry.
    no_executables = work / "no-executables"
    no_executables.mkdir()
    env["PATH"] = str(no_executables)
    assert shutil.which("uv", path=env["PATH"]) is None
    network_before = network.read_bytes()
    switched = cli(*command, "--activate")
    assert switched["activation"] == "changed" and switched["installation"] == "reused"
    assert (
        switched["active_after"]["version"] == "2.0.0"
        and switched["interpreter_verified"]
    )
    assert invoke()["result"] == {"answer": 73}
    repeated = cli(*command, "--activate")
    assert (
        repeated["activation"] == "unchanged" and repeated["installation"] == "reused"
    )
    assert network.read_bytes() == network_before
    cli(
        "enable",
        "apizr-update-probe",
        "--version",
        "1.0.0",
        *preference,
        structured=False,
    )
    assert invoke()["result"] == {"answer": 42}
    assert len(list((work / "plugins/environments").iterdir())) == 2
    assert old_before == snapshot(old_root)
    for path, data in inputs.items():
        assert Path(path).read_bytes() == data
    after = snapshot(core_root)
    distributions_after = subprocess.check_output(
        [sys.executable, "-I", "-B", "-c", inventory], timeout=20
    )
    old_distributions_after = subprocess.check_output(
        [source["python"], "-I", "-B", "-c", inventory], timeout=20
    )
    (work / "core-evidence.json").write_text(
        json.dumps(
            {
                "before": before,
                "after": after,
                "old_before": old_before,
                "old_after": snapshot(old_root),
                "distributions_before": json.loads(distributions_before),
                "distributions_after": json.loads(distributions_after),
                "old_distributions_before": json.loads(old_distributions_before),
                "old_distributions_after": json.loads(old_distributions_after),
            },
            indent=2,
        )
        + "\n"
    )
    assert before == after and distributions_before == distributions_after
    assert old_distributions_before == old_distributions_after
    # The same minimal installed core now retires A after selecting B explicitly.
    cli(
        "enable",
        "apizr-update-probe",
        "--version",
        "2.0.0",
        *preference,
        structured=False,
    )
    new_root = Path(switched["target_installation"]["python"]).parents[2]
    new_before = snapshot(new_root)
    remove = [
        "uninstall",
        "apizr-update-probe",
        "--version",
        "1.0.0",
        *preference,
        "--json",
    ]
    assert cli(*remove, "--dry-run")["state"] == "planned"
    assert snapshot(old_root) == old_before
    assert cli(*remove)["state"] == "complete"
    assert not old_root.exists()
    assert invoke()["result"] == {"answer": 73}
    assert cli(*remove)["state"] == "absent"
    assert (
        cli(
            "uninstall",
            "apizr-update-probe",
            "--version",
            "2.0.0",
            *preference,
            "--json",
            expected=1,
        )["state"]
        == "active"
    )
    assert snapshot(new_root) == new_before
    assert snapshot(core_root) == before
    assert (
        subprocess.check_output(
            [sys.executable, "-I", "-B", "-c", inventory], timeout=20
        )
        == distributions_before
    )
    assert network.read_bytes() == network_before
    for path, data in inputs.items():
        assert Path(path).read_bytes() == data
    summary = {
        "core_unchanged": True,
        "uninstall_complete_and_idempotent": True,
        "active_version_preserved": True,
        "old_environment_unchanged": True,
        "artifacts_unchanged": True,
        "dry_run_unchanged": True,
        "offline_uv": True,
        "uv_failure_recovered": True,
        "prepare_preserves_activation": True,
        "transition_and_retry_without_uv": True,
        "explicit_rollback": True,
        "answers": [42, 42, 73, 42],
    }
    (work / "update-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        "PASS: installed offline update, conditional activation, idempotence and explicit rollback"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("core_root", type=Path)
    args = parser.parse_args()
    prove(args.work.resolve(), args.core_root.resolve())

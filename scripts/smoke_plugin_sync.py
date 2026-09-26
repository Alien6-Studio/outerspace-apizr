"""Installed-core sync proof; run under OS network isolation, outside checkout."""

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def snapshot(root: Path) -> dict[str, str]:
    """Include additions/deletions, file bytes/modes and symlink targets; no exclusions."""
    result = {}
    for path in sorted(root.rglob("*")):
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            value = "link:" + os.readlink(path)
        elif path.is_file():
            value = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            value = "directory"
        result[path.relative_to(root).as_posix()] = f"{mode:o}:{value}"
    return result


def prove(work: Path, core_root: Path) -> None:
    import apizr

    assert not Path(apizr.__file__).resolve().is_relative_to(REPO)
    assert not work.is_relative_to(REPO)
    uv = shutil.which("uv")
    assert uv is not None
    before = snapshot(core_root)
    inventory_program = "import importlib.metadata,json; print(json.dumps(sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions())))"
    before_distributions = subprocess.check_output(
        [sys.executable, "-I", "-B", "-c", inventory_program], cwd=work, timeout=20
    )
    wheels_before = snapshot(work / "wheels")
    wrapper = work / "backend"
    wrapper.mkdir()
    failure = work / "fail-b"
    network_evidence = work / "backend-network.jsonl"
    # Trusted test adapter. Every real uv child inherits the same OS network
    # namespace/sandbox. Force an actual uv refusal for B, without changing bytes.
    (wrapper / "uv").write_text(
        f"#!{sys.executable} -B\n"
        "import json,os,pathlib,socket,sys\n"
        "try:\n socket.create_connection(('1.1.1.1',443),timeout=0.25).close()\n"
        "except OSError:\n denied=True\n"
        "else:\n raise SystemExit('network isolation missing')\n"
        f"with open({str(network_evidence)!r},'a') as stream: stream.write(json.dumps({{'denied':True,'pid':os.getpid()}})+'\\n')\n"
        "args=sys.argv[1:]\n"
        f"if pathlib.Path({str(failure)!r}).exists() and '--requirements' in args:\n"
        " data=pathlib.Path(args[args.index('--requirements')+1]).read_text()\n"
        " if 'apizr-sync-b==' in data: args.append('--apizr-test-invalid-option')\n"
        f"os.execv({uv!r},[{uv!r},*args])\n"
    )
    (wrapper / "uv").chmod(0o700)
    env = dict(
        os.environ,
        PATH=str(wrapper) + os.pathsep + os.environ.get("PATH", ""),
        PYTHONDONTWRITEBYTECODE="1",
        APIZR_TEST_SECRET="sync-secret-must-not-leak",
    )
    reports: list[dict] = []

    def cli(*args: str, expected: int = 0) -> dict:
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-m", "apizr.cli", "plugins", *args],
            cwd=work,
            env=env,
            text=True,
            capture_output=True,
            timeout=150,
        )
        assert "sync-secret-must-not-leak" not in result.stdout + result.stderr
        assert result.returncode == expected, (
            result.returncode,
            result.stdout,
            result.stderr,
        )
        value = json.loads(result.stdout)
        reports.append(
            {"arguments": list(args), "exit_code": result.returncode, "result": value}
        )
        (work / "sync-evidence.json").write_text(json.dumps(reports, indent=2) + "\n")
        return value

    common = [
        "--project",
        str(work / "apizr.toml"),
        "--lock",
        str(work / "apizr.plugins.lock.json"),
        "--wheelhouse",
        str(work / "wheels"),
        "--user-config",
        str(work / "user.toml"),
        "--json",
    ]
    cli(
        "lock",
        "create",
        "--project",
        str(work / "apizr.toml"),
        "--wheelhouse",
        str(work / "wheels"),
        "--output",
        str(work / "apizr.plugins.lock.json"),
        "--json",
    )
    artifacts = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in work.glob("*.lock*")
    }
    preview = cli("sync", *common, "--dry-run")
    assert preview["state"] == "planned" and not (work / "plugins").exists()
    assert not network_evidence.exists()  # No backend during simulation.
    failure.touch()
    partial = cli("sync", *common, expected=2)
    assert partial["state"] == "partial"
    assert [p["status"] for p in partial["plugins"]] == ["installed", "failed"]
    installed_a = json.loads((work / "plugins/installations.json").read_text())[
        "installations"
    ][0]
    failure.unlink()
    complete = cli("sync", *common)
    assert [p["status"] for p in complete["plugins"]] == ["reused", "installed"]
    assert all(
        p["interpreter_verified"] and not p["active"] for p in complete["plugins"]
    )
    installed = json.loads((work / "plugins/installations.json").read_text())[
        "installations"
    ]
    assert installed[0] == installed_a and len(installed) == 2
    assert len(list((work / "plugins/environments").iterdir())) == 2
    cli("lock", "check", *common, "--installed")
    assert (
        cli("list", "--active", "--user-config", str(work / "user.toml"), "--json")[
            "installations"
        ]
        == []
    )
    store_before = snapshot(work / "plugins")
    network_before = network_evidence.read_bytes()
    again = cli("sync", *common)
    assert [p["status"] for p in again["plugins"]] == ["reused", "reused"]
    assert snapshot(work / "plugins") == store_before
    assert network_evidence.read_bytes() == network_before
    for name, answer in [("apizr-sync-a", 42), ("apizr-sync-b", 73)]:
        # enable has human output; run is always structured.
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-m",
                "apizr.cli",
                "plugins",
                "enable",
                name,
                "--version",
                "1.0.0",
                "--user-config",
                str(work / "user.toml"),
            ],
            cwd=work,
            env=env,
            check=True,
            timeout=30,
        )
        assert cli(
            "run",
            name,
            "answer",
            "--arguments",
            str(work / "arguments.json"),
            "--user-config",
            str(work / "user.toml"),
        )["result"] == {"answer": answer}
    assert snapshot(work / "wheels") == wheels_before
    assert artifacts == {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in work.glob("*.lock*")
    }
    after_distributions = subprocess.check_output(
        [sys.executable, "-I", "-B", "-c", inventory_program], cwd=work, timeout=20
    )
    after = snapshot(core_root)
    (work / "core-evidence.json").write_text(
        json.dumps(
            {
                "before": before,
                "after": after,
                "distributions_before": json.loads(before_distributions),
                "distributions_after": json.loads(after_distributions),
            },
            indent=2,
        )
        + "\n"
    )
    assert before_distributions == after_distributions and before == after
    (work / "sync-summary.json").write_text(
        json.dumps(
            {
                "core_unchanged": True,
                "artifacts_unchanged": True,
                "partial_resumed": True,
                "idempotent": True,
                "inactive_until_enabled": True,
                "uv_children_network_denied": True,
                "dependency_answers": [42, 73],
            },
            indent=2,
        )
        + "\n"
    )
    print(
        "PASS: offline sync, partial resume, two closures, idempotence, unchanged installed core"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("core_root", type=Path)
    args = parser.parse_args()
    prove(args.work.resolve(), args.core_root.resolve())

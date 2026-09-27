"""Test-owned operator grants and effect traps for installed publication proofs."""

import json
import subprocess


def write_policy(python, store, path, name, operation, repositories, command):
    inventory = json.loads(
        command(
            python,
            "-I",
            "-B",
            "-m",
            "apizr.cli",
            "plugins",
            "list",
            "--active",
            "--json",
            "--plugins-dir",
            store,
        )
    )
    record = next(r for r in inventory["installations"] if r["name"] == name)
    identity = {
        k: record[k]
        for k in ("name", "version", "sha256", "lock_sha256", "dependencies")
    }
    document = {
        "schema": "apizr.operator-policy/v1",
        "grants": [
            {
                "plugin": identity,
                "operation": operation,
                "repository": repository,
                "permissions": ["registry.read", "registry.publish"],
            }
            for repository in repositories
        ],
    }
    path.write_text(json.dumps(document))
    return path


def write_signing_policy(python, store, path, arguments, command):
    write_policy(
        python,
        store,
        path,
        "apizr-attest",
        "attest",
        [arguments["expected_reference"].split("@")[0]],
        command,
    )
    raw = json.loads(path.read_bytes())
    grant = raw["grants"][0]
    grant.update(
        {
            key: arguments[key]
            for key in ("key_id", "expected_signer", "key_file", "tsa_url")
        }
    )
    grant["permissions"] = ["registry.read", "receipt.sign", "timestamp.request"]
    path.write_text(json.dumps(raw))
    return path


GUARD = """import sys,json
credentials=json.loads(sys.argv[1])
def guard(event,args):
    if event in {"subprocess.Popen","os.system","os.exec","socket.connect","socket.getaddrinfo"}:
        raise AssertionError("effect before operator authorization")
    if event=="open" and str(args[0]) in credentials:
        raise AssertionError("credentials read before operator authorization")
sys.addaudithook(guard)
from apizr.cli import main
raise SystemExit(main(sys.argv[2:]))
"""


def refuse(
    python, store, work, name, operation, arguments, selected, code, environment
):
    path = work / "operator-denied-arguments.json"
    path.write_text(json.dumps(arguments))
    auth = arguments.get(
        "authentication", arguments.get("transport", {}).get("authentication", {})
    )
    credentials = [str(v) for v in auth.values() if v is not None]
    credentials += [str(arguments[k]) for k in ("key_file",) if k in arguments]
    credentials += [str(arguments["docker"]["socket"])] if "docker" in arguments else []
    result = subprocess.run(
        [
            str(python),
            "-I",
            "-B",
            "-c",
            GUARD,
            json.dumps(credentials),
            "plugins",
            "run",
            name,
            operation,
            "--arguments",
            str(path),
            "--plugins-dir",
            str(store),
            *(["--operator-policy", str(selected)] if selected is not None else []),
        ],
        cwd=work,
        env=environment,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 2 and not result.stdout, (result.stdout, result.stderr)
    assert json.loads(result.stderr) == {
        "schema": "apizr.operator-decision/v1",
        "allowed": False,
        "code": code,
    }, result.stderr
    return {"operation": operation, "code": code, "before_effect": True}

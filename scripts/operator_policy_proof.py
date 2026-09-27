"""Test-owned operator grants and effect traps for installed publication proofs."""

import json
import subprocess
from pathlib import Path


def installed_identity(python, store, name, command):
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
    return {
        k: record[k]
        for k in ("name", "version", "sha256", "lock_sha256", "dependencies")
    }


def write_policy(python, store, path, name, operation, repositories, command):
    identity = installed_identity(python, store, name, command)
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


def write_build_policy(python, store, path, arguments, command):
    identity = installed_identity(python, store, "apizr-oci", command)
    target = {
        k: arguments[k]
        for k in (
            "bundle",
            "requirements",
            "wheelhouse",
            "interface",
            "platform",
            "base_image",
            "docker",
            "tag",
        )
    }
    path.write_text(
        json.dumps(
            {
                "schema": "apizr.operator-policy/v1",
                "grants": [
                    {
                        "plugin": identity,
                        "operation": "build",
                        "target": target,
                        "permissions": ["image.build", "registry.read"],
                    }
                ],
            }
        )
    )
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


EFFECT_GUARD = """import sys,json
credentials=json.loads(sys.argv[1])
def guard(event,args):
    if event in {"subprocess.Popen","os.system","os.exec","socket.connect","socket.getaddrinfo"}:
        raise AssertionError("effect before operator authorization")
    if event in {"open", "os.listdir", "os.scandir"} and any(str(args[0]) == p or str(args[0]).startswith(p.rstrip("/")+"/") for p in credentials):
        raise AssertionError("protected input read before operator authorization")
sys.addaudithook(guard)
"""

GUARD = (
    EFFECT_GUARD
    + """
from apizr.cli import main
raise SystemExit(main(sys.argv[2:]))
"""
)


def refuse(
    python, store, work, name, operation, arguments, selected, code, environment
):
    path = work / "operator-denied-arguments.json"
    path.write_text(json.dumps(arguments))
    auth = arguments.get(
        "authentication", arguments.get("transport", {}).get("authentication", {})
    )
    credentials = [str(v) for v in auth.values() if v is not None]
    credentials += [
        str(arguments[k])
        for k in ("key_file", "bundle", "requirements", "wheelhouse")
        if k in arguments
    ]
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


def write_git_policy(
    path,
    repository,
    reference,
    *,
    subdir=".",
    ssh_agent_socket=None,
    ssh_known_hosts=None,
):
    target = {
        "transport": "ssh" if ssh_agent_socket is not None else "https",
        "repository": repository,
        "reference": reference,
        "subdir": subdir,
        "ca_file": None,
        "ssh_agent_socket": str(Path(ssh_agent_socket).absolute())
        if ssh_agent_socket is not None
        else None,
        "ssh_known_hosts": str(Path(ssh_known_hosts).absolute())
        if ssh_known_hosts is not None
        else None,
    }
    path.write_text(
        json.dumps(
            {
                "schema": "apizr.operator-policy/v1",
                "grants": [
                    {
                        "adapter": "git",
                        "operation": "fetch",
                        "target": target,
                        "permissions": ["git.fetch"],
                    },
                    {
                        "adapter": "repository",
                        "operation": "analyze",
                        "permissions": ["source.analyze"],
                        "target": {
                            "kind": "git",
                            "repository": repository,
                            "reference": reference,
                            "subdir": subdir,
                        },
                    },
                ],
            }
        )
    )
    return path


def refuse_git(
    python,
    root,
    environment,
    repository,
    reference,
    *,
    subdir=".",
    ssh_agent_socket=None,
    ssh_known_hosts=None,
):
    """Installed CLI/API refusal with traps before any acquisition effect."""
    options = {
        "subdir": subdir,
        "ssh_agent_socket": str(ssh_agent_socket)
        if ssh_agent_socket is not None
        else None,
        "ssh_known_hosts": str(ssh_known_hosts)
        if ssh_known_hosts is not None
        else None,
    }
    arguments = [
        "readiness",
        "--git",
        repository,
        "--ref",
        reference,
        "--subdir",
        subdir,
        "--report",
    ]
    for name in ("ssh_agent_socket", "ssh_known_hosts"):
        if options[name] is not None:
            arguments.extend(["--" + name.replace("_", "-"), options[name]])
    probe = (
        EFFECT_GUARD
        + """
from pathlib import Path
from apizr.git_source import acquire_snapshot
from apizr.operator_policy import AuthorizationDenied
import apizr.git_source.acquisition as acquisition
def forbidden(*args, **kwargs): raise AssertionError("workspace before admission")
acquisition.TemporaryDirectory = forbidden
request = json.loads(sys.argv[2])
if request['entry'].startswith('cli'):
    from apizr.cli import main
    assert main(request['arguments']) == 2
else:
    options = request['options']
    for name in ('ssh_agent_socket', 'ssh_known_hosts'):
        if options[name] is not None: options[name] = Path(options[name])
    try:
        with acquire_snapshot(request['repository'], request['reference'], **options):
            raise AssertionError('unauthorized acquisition')
    except AuthorizationDenied as error:
        print(error.decision.model_dump_json(by_alias=True), file=sys.stderr)
"""
    )
    results = []
    for entry in ("cli", "api", "cli-fetch-only"):
        flags = arguments
        expected = "operator_policy_required"
        if entry == "cli-fetch-only":
            path = write_git_policy(
                root / "fetch-only.json",
                repository,
                reference,
                subdir=subdir,
                ssh_agent_socket=ssh_agent_socket,
                ssh_known_hosts=ssh_known_hosts,
            )
            raw = json.loads(path.read_bytes())
            raw["grants"] = [g for g in raw["grants"] if g["operation"] == "fetch"]
            path.write_text(json.dumps(raw))
            flags = [*arguments, "--operator-policy", str(path)]
            expected = "operator_operation_denied"
        result = subprocess.run(
            [
                str(python),
                "-I",
                "-B",
                "-c",
                probe,
                json.dumps(
                    [v for k, v in options.items() if k != "subdir" and v is not None]
                ),
                json.dumps(
                    {
                        "entry": entry,
                        "arguments": flags,
                        "repository": repository,
                        "reference": reference,
                        "options": options,
                    }
                ),
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0 and not result.stdout, result.stderr
        decision = json.loads(result.stderr)
        assert decision["code"] == expected and not decision["allowed"]
        results.append(
            {"entrypoint": entry, "code": decision["code"], "before_effect": True}
        )
    (root / "operator-git-refusals.json").write_text(json.dumps(results))


def write_analysis_policy(path, *sources):
    """Write exact local fixture grants; no source enumeration or imports."""
    path.write_text(
        json.dumps(
            {
                "schema": "apizr.operator-policy/v1",
                "grants": [
                    {
                        "adapter": "repository",
                        "operation": "analyze",
                        "target": {
                            "kind": "local",
                            "root": str(Path(source).absolute()),
                        },
                        "permissions": ["source.analyze"],
                    }
                    for source in sources
                ],
            }
        )
    )
    return path


def refuse_analysis(python, work, source):
    """Installed CLI/Python refusals, with source I/O and process/network effect traps."""
    probe = (
        EFFECT_GUARD
        + """
from pathlib import Path
from apizr.operator_policy import AuthorizationDenied, load_operator_policy
from apizr.compiler import assess_readiness
from apizr.cli import main
request = json.loads(sys.argv[2])
if request['entry'] == 'cli':
    flags = ['--operator-policy', request['policy']] if request['policy'] else []
    assert main(['readiness', request['source'], '--report', *flags]) == 2
else:
    operator = load_operator_policy(Path(request['policy'])) if request['policy'] else None
    try:
        assess_readiness(request['source'], operator_policy=operator)
        raise AssertionError('analysis without admission')
    except AuthorizationDenied as error:
        print(error.decision.model_dump_json(by_alias=True), file=sys.stderr)
"""
    )
    results = []
    for entry in ("cli", "api"):
        for case, code in [
            ("missing", "operator_policy_required"),
            ("neighbor", "operator_analysis_denied"),
        ]:
            selected = None
            if case == "neighbor":
                selected = write_analysis_policy(
                    work / "denied-analysis.json",
                    source.parent / (source.name + "-other"),
                )
            result = subprocess.run(
                [
                    str(python),
                    "-I",
                    "-B",
                    "-c",
                    probe,
                    json.dumps([str(source)]),
                    json.dumps(
                        {
                            "entry": entry,
                            "source": str(source),
                            "policy": str(selected) if selected else None,
                        }
                    ),
                ],
                cwd=work,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0 and not result.stdout, result.stderr
            decision = json.loads(result.stderr)
            assert not decision["allowed"] and decision["code"] == code
            results.append({"entry": entry, "case": case, "decision": decision})
    (work / "operator-analysis-refusals.json").write_text(json.dumps(results))


GIT_ANALYSIS_REFUSAL = """
def verify_analysis_refusal(snapshot):
    import os
    import apizr.repository.discovery as discovery
    from apizr.compiler import assess_readiness
    from apizr.operator_policy import AuthorizationDenied, load_operator_policy
    from pathlib import Path
    selected = load_operator_policy(Path("operator.json"))
    fetch_only = selected.model_copy(update={"grants": tuple(g for g in selected.grants if g.operation == "fetch")})
    original_scan, original_read = os.scandir, discovery.read_source
    def forbidden(*args, **kwargs):
        raise AssertionError("source read before analysis admission")
    os.scandir = discovery.read_source = forbidden
    try:
        for authority, expected in ((None, "operator_policy_required"), (fetch_only, "operator_operation_denied")):
            try:
                assess_readiness(snapshot, operator_policy=authority)
                raise AssertionError("analysis without source permission")
            except AuthorizationDenied as error:
                assert error.code == expected
    finally:
        os.scandir, discovery.read_source = original_scan, original_read
"""

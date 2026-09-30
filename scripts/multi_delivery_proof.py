"""Real managed batches in the existing authenticated registry/TSA fixture."""

import hashlib
import json
import subprocess
from pathlib import Path

from operator_policy_proof import installed_identity


def exercise(
    python,
    store,
    work,
    builds,
    signing,
    command,
    environment,
    tsa_calls,
    *,
    mcp_python=None,
):
    prefix = "mcp-batch" if mcp_python is not None else "batch"
    oras = Path("/opt/oras/oras")
    transport_tool = {
        "executable": str(oras),
        "version": "1.3.4",
        "sha256": hashlib.sha256(oras.read_bytes()).hexdigest(),
    }
    trace = work / (prefix + "-managed-calls.jsonl")
    driver = work / (prefix + "-driver.py")
    driver.write_text("""import json,sys
from pathlib import Path
from apizr.delivery_batch import operations
from apizr.cli import main
original=operations.run_extension
def tracked(name, operation, arguments, **kwargs):
    assert operation != 'build', 'batch must never invoke build'
    with Path(sys.argv[1]).open('a') as stream:
        stream.write(json.dumps({'plugin':name,'operation':operation,'destination':arguments.get('destination',arguments.get('push',{}).get('destination')),'reference':arguments.get('expected_reference')})+'\\n')
    reply=original(name,operation,arguments,**kwargs)
    if operation in {'push','admit'}:
        import subprocess,tempfile
        authentication=arguments['authentication'] if operation=='push' else arguments['transport']['authentication']
        with tempfile.TemporaryDirectory() as config:
            Path(config,'config.json').write_bytes(Path(authentication['config_file']).read_bytes())
            observed=subprocess.run(['/usr/local/bin/docker','--config',config,'manifest','inspect','--verbose',arguments['destination']],capture_output=True,timeout=15)
        if operation=='push':
            assert observed.returncode != 0 and b'no such manifest:' in observed.stderr
        else:
            assert observed.returncode == 0
            remote=json.loads(observed.stdout)
            assert remote['Descriptor']['digest']==reply.result['image_reference'].split('@')[1]
        with Path(sys.argv[1]+'.checkpoints').open('a') as stream:
            stream.write(json.dumps({'destination':arguments['destination'],'stage':operation,'tag_absent':operation=='push'})+'\\n')
    return reply
operations.run_extension=tracked
raise SystemExit(main(sys.argv[2:]))
""")
    docker = work / (prefix + "-docker")
    docker_log = work / (prefix + "-docker-calls.jsonl")
    docker.write_text(f"""#!/usr/bin/python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
assert args and args[0] != 'build', 'batch must never rebuild'
with Path({str(docker_log)!r}).open('a') as stream:
 stream.write(json.dumps(args)+'\\n')
os.execv('/usr/local/bin/docker',['/usr/local/bin/docker',*args])
""")
    docker.chmod(0o700)
    oci = installed_identity(python, store, "outerspace-apizr-oci", command)
    attest = installed_identity(python, store, "outerspace-apizr-attest", command)
    before_builds = (work / "successful-builds.jsonl").read_bytes()
    completed = []
    for interface, built in zip(("rest", "mcp"), builds, strict=True):
        build = built["result"]
        successes = [json.loads(line) for line in before_builds.splitlines()]
        assert (
            sum(
                json.loads(item["--iidfile"]) == build["image_id"]
                if item["--iidfile"].startswith('"')
                else item["--iidfile"].strip() == build["image_id"]
                for item in successes
            )
            == 1
        )
        destinations, grants = [], []
        broken_key = work / (prefix + "-" + interface + "-b.key")
        for scope in ("a", "b", "c"):
            repository = f"registry.test:5443/batch-{scope}/{interface}"
            auth = {
                "config_file": f"/proof/auth/batch-{scope}.json",
                "ca_file": "/proof/certs/ca.crt",
            }
            push = {
                "schema": "apizr.oci-push/v1",
                **{
                    k: build[k]
                    for k in (
                        "image_id",
                        "platform",
                        "inputs_sha256",
                        "delivery_plan",
                        "delivery_manifest",
                    )
                },
                "destination": repository
                + (":mcp-v1" if mcp_python is not None else ":v1"),
                "docker": {
                    "executable": str(docker),
                    "socket": "/proof/builder.sock",
                    "buildx": "/usr/local/libexec/docker/cli-plugins/docker-buildx",
                },
                "authentication": auth,
            }
            sign = {k: signing[k] for k in ("key_id", "key_file", "tsa_url")}
            if scope == "b":
                sign["key_file"] = str(broken_key)
            verify = {k: signing[k] for k in ("expected_signer", "trust_store", "tool")}
            destinations.append(
                {
                    "push": push,
                    "proof": {
                        "verification": verify,
                        "signing": sign,
                        "transport": {"tool": transport_tool, "authentication": auth},
                    },
                }
            )
            for operation, plugin, permissions in (
                ("push", oci, ["registry.read", "registry.publish"]),
                ("observe", oci, ["registry.read"]),
                ("publish", attest, ["registry.read", "registry.publish"]),
                ("admit", attest, ["registry.read", "registry.publish"]),
                (
                    "attest",
                    attest,
                    ["registry.read", "receipt.sign", "timestamp.request"],
                ),
            ):
                grant = {
                    "plugin": plugin,
                    "operation": operation,
                    "repository": repository,
                    "permissions": permissions,
                }
                if operation == "attest":
                    grant.update(sign | {"expected_signer": signing["expected_signer"]})
                grants.append(grant)
        project = None
        if mcp_python is not None:
            project_root = work / (prefix + "-" + interface + "-project")
            project_root.mkdir()
            project = project_root / "apizr.toml"
            project.write_text('schema_version="apizr.project/v1"\nroot="."\n')
            grants.append(
                {
                    "adapter": "repository",
                    "operation": "analyze",
                    "target": {"kind": "local", "root": str(project_root)},
                    "permissions": ["source.analyze"],
                }
            )
        policy = work / (prefix + "-" + interface + "-policy.json")
        policy.write_text(
            json.dumps({"schema": "apizr.operator-policy/v1", "grants": grants})
        )
        request = work / (prefix + "-" + interface + "-request.json")
        request.write_text(
            json.dumps(
                {
                    "schema": "apizr.delivery-batch-request/v1",
                    "build": build,
                    "destinations": destinations,
                    "evidence_root": str(
                        work / (prefix + "-" + interface + "-evidence")
                    ),
                }
            )
        )

        def invoke(
            mode,
            expected,
            request=request,
            policy=policy,
            interface=interface,
            project=project,
        ):
            invocation = [
                str(python),
                "-I",
                "-B",
                str(driver),
                str(trace),
                "delivery",
                mode,
                "--request",
                str(request),
                "--operator-policy",
                str(policy),
                "--plugins-dir",
                str(store),
            ]
            if mcp_python is not None:
                config = work / (prefix + "-" + interface + "-session.json")
                config.write_text(
                    json.dumps(
                        {
                            "cli": str(python.parent / "apizr"),
                            "project": str(project),
                            "policy": str(policy),
                            "store": str(store),
                            "request": str(request),
                        }
                    )
                )
                invocation = [
                    str(mcp_python),
                    "-I",
                    "-B",
                    "/repo/scripts/mcp_delivery_client.py",
                    "--config",
                    str(config),
                    "--operation",
                    mode,
                    "--expected-state",
                    "partial" if expected else "complete",
                    *(["--legacy"] if interface == "mcp" else []),
                ]
            reply = subprocess.run(
                invocation,
                env=environment,
                cwd=work,
                capture_output=True,
                timeout=300,
            )
            assert reply.returncode == (0 if mcp_python is not None else expected), (
                reply.returncode,
                reply.stdout,
                reply.stderr,
            )
            result = json.loads(reply.stdout)
            assert result["state"] == ("partial" if expected else "complete"), result
            return result

        if mcp_python is not None:
            full = json.loads(request.read_text())
            full["destinations"] = [full["destinations"][0]]
            full["destinations"][0]["push"]["destination"] = (
                full["destinations"][0]["push"]["destination"].rsplit(":", 1)[0]
                + ":mcp-complete"
            )
            full["evidence_root"] = str(
                work / (prefix + "-" + interface + "-full-evidence")
            )
            full_request = work / (prefix + "-" + interface + "-full-request.json")
            full_request.write_text(json.dumps(full))
            fully_delivered = invoke("run", 0, request=full_request)
            assert fully_delivered["state"] == "complete"
            (work / (prefix + "-" + interface + "-run-complete.json")).write_text(
                json.dumps(fully_delivered, indent=2)
            )
        started = len(tsa_calls)
        partial = invoke("run", 1)
        assert [o["state"] for o in partial["outcomes"]] == [
            "complete",
            "failed",
            "complete",
        ]
        assert partial["outcomes"][1]["last_confirmed_stage"] == "transferred"
        assert partial["outcomes"][1]["diagnostic"] == "attestation_failed"
        assert len(tsa_calls) - started == 2
        # B's transferred image is real; its destination has never been promoted.
        b = destinations[1]["push"]
        auth_dir = work / (
            (prefix + "-" if mcp_python is not None else "") + interface + "-b-auth"
        )
        auth_dir.mkdir()
        (auth_dir / "config.json").write_bytes(
            Path(b["authentication"]["config_file"]).read_bytes()
        )
        absent = subprocess.run(
            [
                "/usr/local/bin/docker",
                "--config",
                str(auth_dir),
                "manifest",
                "inspect",
                b["destination"],
            ],
            capture_output=True,
            timeout=15,
        )
        assert absent.returncode != 0 and b"no such manifest:" in absent.stderr
        # Separate actual authentication scope: credentials A cannot read repository C.
        import base64

        a_auth = json.loads(
            Path(destinations[0]["push"]["authentication"]["config_file"]).read_bytes()
        )["auths"]["registry.test:5443"]["auth"]
        status = command(
            "curl",
            "--silent",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            "--cacert",
            "/proof/certs/ca.crt",
            "--user",
            base64.b64decode(a_auth).decode(),
            f"https://registry.test:5443/v2/batch-c/{interface}/tags/list",
        )
        assert status in {"401", "403"}, status
        # Correct only B's missing key, retaining the same request and grants.
        broken_key.write_bytes(Path(signing["key_file"]).read_bytes())
        broken_key.chmod(0o600)
        calls_before_resume = len(
            (docker_log if mcp_python is not None else trace).read_text().splitlines()
        )
        recovered = invoke("resume", 0)
        broken_key.unlink()
        assert len(tsa_calls) - started == 3
        resumed_calls = [
            json.loads(line)
            for line in (docker_log if mcp_python is not None else trace)
            .read_text()
            .splitlines()[calls_before_resume:]
        ]
        if mcp_python is None:
            assert not any(
                item["operation"] in {"build", "push"} for item in resumed_calls
            )
            assert sum(item["operation"] == "attest" for item in resumed_calls) == 1
        else:
            assert not any(
                token in {"build", "push"} for call in resumed_calls for token in call
            )
            # The shared TSA counts independently establish exactly one B signature.
            assert not (work / "git-proof").exists()
            assert not (work / "application-bundles").exists()
        for index in (0, 2):
            assert (
                recovered["outcomes"][index]["proof"]
                == partial["outcomes"][index]["proof"]
            )
            assert (
                recovered["outcomes"][index]["publication"]
                == partial["outcomes"][index]["publication"]
            )
            assert (
                recovered["outcomes"][index]["admission"]
                == partial["outcomes"][index]["admission"]
            )
        for item in recovered["outcomes"]:
            assert item["transfer"]["image_id"] == build["image_id"]
            assert item["transfer"]["inputs_sha256"] == build["inputs_sha256"]
            assert (
                item["transfer"]["delivery_manifest_digest"]
                == build["delivery_manifest_digest"]
            )
            assert (
                item["admission"]["delivery_plan_digest"]
                == build["delivery_manifest"]["delivery_plan_digest"]
            )
        (work / (prefix + "-" + interface + "-partial.json")).write_text(
            json.dumps(partial, indent=2)
        )
        (work / (prefix + "-" + interface + "-complete.json")).write_text(
            json.dumps(recovered, indent=2)
        )
        completed.append(
            {
                "interface": interface,
                "build_operations": 1,
                "delivery_build_operations": 0,
                "resume_build_operations": 0,
                "partial": partial,
                "recovered": recovered,
                "resume_signatures": 1,
                "independent_auth_scopes": True,
                "b_tag_absent_before_admission": True,
            }
        )
    assert (work / "successful-builds.jsonl").read_bytes() == before_builds
    (
        work
        / (
            "mcp-delivery-results.json"
            if mcp_python is not None
            else "multi-delivery-results.json"
        )
    ).write_text(json.dumps(completed, indent=2))
    print(
        "PASS real REST/MCP multi-destination partial A/B/C and resume; one build per interface, independent credentials, no duplicate signing",
        flush=True,
    )

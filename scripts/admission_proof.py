"""Mandatory-proof checkpoints inside the existing disposable registry proof."""

import json
import subprocess
import sys
from pathlib import Path

from operator_policy_proof import refuse, write_policy


def exercise(python, store, work, builds, pushes, rest, mcp, command, environment):
    record = json.loads((work / "artifact-results.json").read_bytes())
    transport = {"tool": record["oras"], "authentication": rest["authentication"]}
    repositories = [p["destination"].rsplit(":", 1)[0] for p in pushes]
    operator = write_policy(
        python,
        store,
        work / "operator-admit.json",
        "outerspace-apizr-attest",
        "admit",
        repositories,
        command,
    )
    publisher = write_policy(
        python,
        store,
        work / "operator-mcp-publish.json",
        "outerspace-apizr-attest",
        "publish",
        repositories,
        command,
    )
    base = [
        str(python),
        "-I",
        "-B",
        "-m",
        "apizr.cli",
        "plugins",
        "run",
        "outerspace-apizr-attest",
    ]
    docker = ["/usr/local/bin/docker", "--config", "/proof/auth"]
    results, refusals = [], []

    def invoke(op, arguments, selected, refused=False):
        path = work / "admission-arguments.json"
        path.write_text(json.dumps(arguments))
        reply = subprocess.run(
            [
                *base,
                op,
                "--arguments",
                str(path),
                "--operator-policy",
                str(selected),
                "--plugins-dir",
                str(store),
                "--timeout-ms",
                "120000",
            ],
            cwd=work,
            env=environment,
            capture_output=True,
            timeout=125,
        )
        if refused:
            assert (
                reply.returncode == 2
                and reply.stdout == b""
                and reply.stderr == b"apizr plugins: plugin_failed\n"
            ), (reply.stdout, reply.stderr)
            return None
        assert reply.returncode == 0, (reply.stdout, reply.stderr)
        return json.loads(reply.stdout)["result"]

    def absent(destination):
        observed = subprocess.run(
            [*docker, "manifest", "inspect", destination],
            capture_output=True,
            timeout=15,
        )
        assert observed.returncode != 0 and b"no such manifest:" in observed.stderr

    for index, signing in enumerate((rest, mcp)):
        pushed = pushes[index]
        absent(pushed["destination"])
        assert not Path(signing["key_file"]).exists()
        common = {
            k: signing[k]
            for k in ("expected_reference", "expected_signer", "trust_store", "tool")
        }
        published = (
            record["published"]
            if index == 0
            else invoke(
                "publish",
                common
                | {
                    "schema": "apizr.publish-proof/v1",
                    "proof_dir": signing["output_dir"],
                    "transport": transport,
                },
                publisher,
            )
        )
        assert (
            published is not None
            and published["state"] == "verified"
            and published["receipt_published"]
        )
        # Explicit value from this specific publication; discovery never chooses.
        arguments = common | {
            "schema": "apizr.admit-delivery/v1",
            "push_result": signing["push_result"],
            "delivery_manifest": builds[index]["result"]["delivery_manifest"],
            "destination": pushed["destination"],
            "artifact_reference": published["artifact_reference"],
            "transport": transport,
            "docker": signing["docker"]
            | {"buildx": "/usr/local/libexec/docker/cli-plugins/docker-buildx"},
        }
        absent(pushed["destination"])
        for selected, code in (
            (None, "operator_policy_required"),
            (publisher, "operator_operation_denied"),
        ):
            refusals.append(
                refuse(
                    python,
                    store,
                    work,
                    "outerspace-apizr-attest",
                    "admit",
                    arguments,
                    selected,
                    code,
                    environment,
                )
            )
        read_only = work / "operator-admit-read-only.json"
        raw = json.loads(operator.read_bytes())
        for grant in raw["grants"]:
            grant["permissions"] = ["registry.read"]
        read_only.write_text(json.dumps(raw))
        refusals.append(
            refuse(
                python,
                store,
                work,
                "outerspace-apizr-attest",
                "admit",
                arguments,
                read_only,
                "operator_permissions_denied",
                environment,
            )
        )
        for fault, change in (
            (
                "absent-proof",
                {"artifact_reference": repositories[index] + "@sha256:" + "0" * 64},
            ),
            ("wrong-signer", {"expected_signer": "0" * 64}),
        ):
            invoke("admit", arguments | change, operator, refused=True)
            absent(pushed["destination"])
            refusals.append(
                {
                    "case": fault,
                    "interface": ("rest", "mcp")[index],
                    "destination_absent": True,
                }
            )
        # An uncertain publication record cannot substitute for the signed transfer.
        fabricated = work / "fabricated-publication.json"
        fabricated.write_text(
            json.dumps(
                published
                | {"state": "remote_state_unconfirmed", "receipt_published": False}
            )
        )
        invoke(
            "admit",
            arguments | {"push_result": str(fabricated)},
            operator,
            refused=True,
        )
        absent(pushed["destination"])
        if index == 0:
            # Corrupt the observation only AFTER the real promotion. Retry must
            # fetch/verify proof again and inspect the existing exact destination.
            marker = work / "admission-promoted"
            wrapper = work / "admission-observer"
            wrapper.write_text(
                f"#!{sys.executable}\n"
                + f"""import os,subprocess,sys
from pathlib import Path
args=sys.argv[1:]
marker=Path({str(marker)!r})
if args[:3]==['buildx','imagetools','create']:
 result=subprocess.run(['/usr/local/bin/docker',*args])
 if result.returncode==0: marker.touch()
 raise SystemExit(result.returncode)
if args[:2]==['manifest','inspect'] and marker.exists():
 print('{{}}')
 raise SystemExit(0)
os.execv('/usr/local/bin/docker',['/usr/local/bin/docker',*args])
"""
            )
            wrapper.chmod(0o700)
            uncertain = invoke(
                "admit",
                arguments
                | {"docker": arguments["docker"] | {"executable": str(wrapper)}},
                operator,
            )
            assert (
                marker.exists()
                and uncertain is not None
                and uncertain["state"] == "remote_state_unconfirmed"
                and not uncertain["delivery_admitted"]
                and uncertain["destination_promoted"] is None
            )
            refusals.append(
                {
                    "case": "post-promotion-observation",
                    "state": uncertain["state"],
                    "rollback": False,
                }
            )
        admitted = invoke("admit", arguments, operator)
        assert (
            admitted is not None
            and admitted["state"] == "admitted"
            and admitted["delivery_admitted"]
            and admitted["destination_promoted"]
        )
        assert invoke("admit", arguments, operator) == admitted
        observed = json.loads(
            command(*docker, "manifest", "inspect", "--verbose", pushed["destination"])
        )
        assert observed["Descriptor"]["digest"] == pushed["manifest_digest"]
        assert observed["OCIManifest"]["config"]["digest"] == pushed["config_digest"]
        results.append(
            {
                "interface": ("rest", "mcp")[index],
                "tag_absent_after_transfer": True,
                "tag_absent_after_invalid_proof": True,
                "tag_absent_after_publication": True,
                "private_key_absent": True,
                "published": published,
                "admission": admitted,
                "idempotent_retry": True,
                "destination_manifest_digest": observed["Descriptor"]["digest"],
            }
        )
    (work / "admission-results.json").write_text(json.dumps(results, indent=2))
    (work / "admission-refusals.json").write_text(json.dumps(refusals, indent=2))
    print(
        "PASS required REST/MCP: absent destination after transfer/invalid proof; verified admission; exact destination; idempotent recovery",
        flush=True,
    )

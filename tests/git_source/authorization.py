"""Explicit test-owned grants for existing transport qualification scenarios."""

import json
from pathlib import Path

from apizr.git_source import acquire_snapshot
from apizr.git_source.contracts import is_ssh
from apizr.operator_policy import OperatorPolicy


def document(
    repository,
    reference,
    *,
    subdir=".",
    ca_file=None,
    ssh_agent_socket=None,
    ssh_known_hosts=None,
    **unused,
):
    return {
        "schema": "apizr.operator-policy/v1",
        "grants": [
            {
                "adapter": "git",
                "operation": "fetch",
                "permissions": ["git.fetch"],
                "target": {
                    "transport": "ssh" if is_ssh(repository) else "https",
                    "repository": repository,
                    "reference": reference,
                    "subdir": subdir,
                    "ca_file": str(Path(ca_file).absolute())
                    if ca_file is not None
                    else None,
                    "ssh_agent_socket": str(Path(ssh_agent_socket).absolute())
                    if ssh_agent_socket is not None
                    else None,
                    "ssh_known_hosts": str(Path(ssh_known_hosts).absolute())
                    if ssh_known_hosts is not None
                    else None,
                },
            }
        ],
    }


def policy(repository, reference, **options):
    return OperatorPolicy.model_validate_json(
        json.dumps(document(repository, reference, **options))
    )


def authorized_snapshot(repository, reference, **options):
    return acquire_snapshot(
        repository,
        reference,
        operator_policy=policy(repository, reference, **options),
        **options,
    )


def flags(directory, repository, reference, **options):
    path = directory / "operator.json"
    value = document(repository, reference, **options)
    value["grants"].append(
        {
            "adapter": "repository",
            "operation": "analyze",
            "permissions": ["source.analyze"],
            "target": {
                "kind": "git",
                "repository": repository,
                "reference": reference,
                "subdir": options.get("subdir", "."),
            },
        }
    )
    path.write_text(json.dumps(value))
    return ["--operator-policy", str(path)]

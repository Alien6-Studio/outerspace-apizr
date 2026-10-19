"""Compare unchanged bundle evidence while asserting the new provenance boundary."""

import json


def assert_equivalent_bundles(first, second):
    first = {str(k): v for k, v in first.items()}
    second = {str(k): v for k, v in second.items()}
    name = "apizr-bundle-provenance.json"
    a, b = (json.loads(value.pop(name)) for value in (first, second))
    assert a["generator"] == b["generator"]
    assert a["source"]["repository_digest"] == b["source"]["repository_digest"]
    assert {a["source"]["kind"], b["source"]["kind"]} == {"git", "local"}
    remote = a["source"] if a["source"]["kind"] == "git" else b["source"]
    assert (
        remote["repository"]
        and remote["requested_ref"]
        and len(remote["resolved_commit"]) in {40, 64}
    )
    manifest = next(
        k
        for k in first
        if k in {"apizr-repository-rest.json", "apizr-repository-mcp.json"}
    )
    left, right = (json.loads(value.pop(manifest)) for value in (first, second))
    for value in (left, right):
        assert value.pop("provenance_digest") == value["artifacts"].pop(name)
    assert left == right
    assert first == second
    return remote

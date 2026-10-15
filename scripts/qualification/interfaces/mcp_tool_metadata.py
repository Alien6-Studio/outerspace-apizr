"""Offline review of the official plugin's complete public discovery surface."""

from copy import deepcopy

from jsonschema import Draft202012Validator

TITLES = {
    "apizr_analyze": "Analyze Python Project",
    "apizr_readiness": "Assess Repository Readiness",
    "apizr_plan_exposure": "Plan Capability Exposure",
    "apizr_experiment_list": "List Experiment Runs",
    "apizr_experiment_show": "Show Experiment Evidence",
    "apizr_experiment_diff": "Compare Experiment Runs",
    "apizr_delivery_status": "Inspect Delivery Status",
    "apizr_delivery_run": "Run Approved Delivery",
    "apizr_delivery_resume": "Resume Approved Delivery",
}


def input_properties(schema, path=""):
    """Visit schema nodes, never literal examples/defaults or property names as keys."""
    if not isinstance(schema, dict):
        return
    for name, value in schema.get("properties", {}).items():
        yield f"{path}/properties/{name}", value
    for keyword in ("properties", "$defs", "definitions", "patternProperties"):
        for name, value in schema.get(keyword, {}).items():
            yield from input_properties(value, f"{path}/{keyword}/{name}")
    for keyword in ("items", "additionalProperties", "not", "if", "then", "else"):
        yield from input_properties(schema.get(keyword), f"{path}/{keyword}")
    for keyword in ("anyOf", "allOf", "oneOf", "prefixItems"):
        for index, value in enumerate(schema.get(keyword, [])):
            yield from input_properties(value, f"{path}/{keyword}/{index}")


def review(metadata: dict, *, delivery: bool = False) -> list[dict]:
    """A deterministic review matrix, not a remote score or an authorization check."""
    expected = list(TITLES) if delivery else list(TITLES)[:6]
    assert [t["name"] for t in metadata["tools"]] == expected
    assert metadata["server"]["name"] == "apizr"
    assert metadata["server"]["title"] == "OuterSpace Apizr"
    assert metadata["server"]["version"] == "0.4.5"
    rows = []
    for tool in metadata["tools"]:
        name = tool["name"]
        assert tool["title"] == TITLES[name], name
        assert len(tool["description"].split()) >= 10, name
        inputs, outputs = tool["inputSchema"], tool["outputSchema"]
        assert inputs["type"] == "object" and inputs["additionalProperties"] is False
        properties = list(input_properties(inputs))
        for path, value in properties:
            assert len(value.get("description", "").split()) >= 3, (name, path)
        assert outputs and outputs.get("type") == "object", name
        Draft202012Validator.check_schema(inputs)
        Draft202012Validator.check_schema(outputs)
        effectful = name in {"apizr_delivery_run", "apizr_delivery_resume"}
        expected_hints = {
            "readOnlyHint": not effectful,
            "destructiveHint": False,
            "idempotentHint": not effectful,
            "openWorldHint": effectful,
        }
        assert all(tool["annotations"][k] is v for k, v in expected_hints.items())
        if name == "apizr_delivery_status":
            assert inputs["properties"] == {}  # Deliberately takes no arguments.
            assert "no network or mutation" in tool["description"].lower()
        if effectful:
            assert "operator-selected" in tool["description"]
            assert "remote" in tool["description"]
        rows.append(
            {
                "name": name,
                "title": tool["title"],
                "described_input_properties": len(properties),
                "output_schema": True,
                "annotations": expected_hints,
            }
        )
    return rows


def validate_result(tool: dict, response) -> None:
    """A successful MCP call can still carry a failed/limited business result."""
    assert not response.is_error
    Draft202012Validator(tool["outputSchema"]).validate(response.structured_content)


def before_distribution_metadata(metadata: dict) -> dict:
    """Retain the historical #268/#269 surface before #279/#333 additions."""
    prior = deepcopy(metadata)
    # Preserve the historical analysis/delivery contract fingerprint while
    # independently qualifying the additive 0.4.6 history tools and schemas.
    prior["tools"] = [
        tool
        for tool in prior["tools"]
        if not tool["name"].startswith("apizr_experiment_")
    ]
    prior["server"]["title"] = None
    for tool in prior["tools"]:
        tool["title"] = None
        if tool["name"] in {"apizr_delivery_run", "apizr_delivery_resume"}:
            field = tool["inputSchema"]["properties"][
                "expected_delivery_manifest_digest"
            ]
            field.pop("description", None)
    return prior


def before_distribution_responses(responses: dict) -> dict:
    """Only modern SDK serverInfo gains the reviewed human-readable server title."""
    prior = deepcopy(responses)
    for response in prior.values():
        info = (response.get("_meta") or {}).get("io.modelcontextprotocol/serverInfo")
        if info is not None and "title" in info:
            assert info["title"] == "OuterSpace Apizr"
            del info["title"]
    return prior

"""Pure interpretation of provider responses; unavailable evidence never passes."""

from .metadata import NAME, PACKAGES, REPOSITORY_URL


def outcome(status: str, reason: str, **evidence) -> dict:
    return {
        "status": status,
        "verification": "verified" if status == "verified" else "not_verified",
        "reason": reason,
        **evidence,
    }


def pypi(payload: dict, name: str, version: str, artifacts: dict) -> dict:
    info = payload["info"]
    if info["name"].lower().replace("_", "-") != name:
        return outcome("mismatch", "Package identity differs")
    if info["version"] != version:
        return outcome("stale", "Expected version is not the advertised version")
    files = payload["urls"]
    actual = {v["filename"]: v["digests"]["sha256"] for v in files}
    if (
        len(actual) != len(files)
        or actual != artifacts
        or any(v.get("yanked") for v in files)
    ):
        return outcome(
            "mismatch", "Public archive set/digests differ from the qualified release"
        )
    if name == PACKAGES[1] and f"<!-- mcp-name: {NAME} -->" not in info.get(
        "description", ""
    ):
        return outcome("mismatch", "PyPI MCP ownership marker is absent or different")
    return outcome(
        "verified",
        "Exact public version and qualified wheel/sdist digests",
        artifacts=actual,
    )


def official_registry(payload: dict, descriptor: dict) -> dict:
    server = payload["server"]
    if server["name"] != NAME:
        return outcome("mismatch", "Official namespace differs")
    if server["version"] != descriptor["version"]:
        return outcome("stale", "Official Registry version differs")
    official = payload.get("_meta", {}).get(
        "io.modelcontextprotocol.registry/official", {}
    )
    if official.get("status") != "active":
        return outcome("mismatch", "Official Registry entry is not active")
    # The registry may add repository IDs and metadata; every publisher-owned
    # configuration field must still equal the released descriptor exactly.
    for key in ("title", "description", "websiteUrl", "icons", "packages"):
        if server.get(key) != descriptor.get(key):
            return outcome("mismatch", "Released descriptor differs", field=key)
    if any(
        server.get("repository", {}).get(k) != v
        for k, v in descriptor["repository"].items()
    ) or server.get("remotes"):
        return outcome("mismatch", "Repository or transport identity differs")
    return outcome(
        "verified", "Exact active namespace, version, package and configuration"
    )


def compare_tools(actual: list, expected: list, fields: tuple[str, ...]) -> dict:
    if not isinstance(actual, list):
        return outcome("not_checked", "Directory has not exposed a tool surface")
    by_name = {t["name"]: t for t in actual}
    if len(by_name) != len(actual) or set(by_name) != {t["name"] for t in expected}:
        return outcome(
            "stale", "Indexed tool set differs from the qualified analysis surface"
        )
    unavailable = set()
    for tool in expected:
        observed = by_name[tool["name"]]
        for field in fields:
            if field not in observed or observed[field] is None:
                unavailable.add(field)
            elif observed[field] != tool[field]:
                return outcome(
                    "stale",
                    "Indexed tool metadata differs",
                    field=field,
                    tool=tool["name"],
                )
    if unavailable:
        return outcome(
            "not_checked",
            "Directory API does not expose all required tool metadata",
            unexposed_fields=sorted(unavailable),
        )
    return outcome("verified", "Indexed tools match the qualified installed discovery")


def glama(payload: dict, discovery: dict) -> dict:
    listing = "https://glama.ai/mcp/servers/Alien6-Studio/outerspace-apizr"
    attribution = {"source": "MCP data from Glama", "url": listing}
    if (
        payload["namespace"] != "Alien6-Studio"
        or payload["slug"] != "outerspace-apizr"
        or (payload.get("repository") or {}).get("url") != REPOSITORY_URL
        or payload.get("url") != listing
    ):
        return outcome(
            "mismatch",
            "Glama server/repository identity differs",
            attribution=attribution,
        )
    fields = ("description", "inputSchema", "outputSchema")
    if any(tool.get("title") is not None for tool in payload["tools"]):
        fields += ("title",)
    result = compare_tools(
        payload["tools"],
        discovery["tools"],
        fields,
    )
    # Current read API exposes neither titles, initialization nor package version.
    # Never invent them or promote an API limitation into a third-party pass.
    result["attribution"] = attribution
    result["additional_public_page_review"] = ["instructions", "package/version"]
    if "title" not in fields:
        result["additional_public_page_review"].append("tool.title")
    return result


def smithery(
    payload: dict, discovery: dict, manifest: dict, bundle: bytes | None
) -> dict:
    if payload.get("remote") is not False:
        return outcome("mismatch", "Expected a local stdio listing")
    connections = [c for c in payload["connections"] if c.get("type") == "stdio"]
    if len(connections) != 1:
        return outcome("mismatch", "Expected exactly one stdio installation contract")
    schema = connections[0]["configSchema"]
    expected = manifest["user_config"]
    if set(schema.get("required", [])) != set(expected) or set(
        schema.get("properties", {})
    ) != set(expected):
        return outcome(
            "mismatch",
            "Smithery configuration no longer requires exactly the three explicit inputs",
        )
    for key, field in schema["properties"].items():
        if (
            field.get("type") != "string"
            or not field.get("description")
            or "default" in field
        ):
            return outcome(
                "mismatch",
                "Smithery configuration types/descriptions/defaults differ",
                field=key,
            )
    tools = compare_tools(
        payload["tools"],
        discovery["tools"],
        ("description", "inputSchema", "outputSchema"),
    )
    if tools["status"] != "verified":
        return tools
    if bundle is None:
        return outcome(
            "not_checked",
            "Download and verify the listing's actual MCPB to bind its package/repository/version",
        )
    # The caller compares downloaded bytes to the locally reproducible bundle.
    return outcome(
        "verified",
        "Tools/configuration match; exact MCPB binds package, repository and version",
    )


def mcpfinder(rows: list[dict], version: str) -> dict:
    selected = [r for r in rows if r.get("repository_url") == REPOSITORY_URL]
    if not selected:
        return outcome(
            "missing", "No matching repository in the inspected MCPfinder snapshot"
        )
    if len(selected) != 1:
        return outcome(
            "mismatch", "Ambiguous duplicate repository records in the snapshot"
        )
    row = selected[0]
    if row["version"] != version:
        return outcome("stale", "MCPfinder has not propagated the release version")
    if (
        row["package_identifier"] != PACKAGES[1]
        or row["transport_type"] != "stdio"
        or row["status"] != "active"
    ):
        return outcome("mismatch", "MCPfinder package/transport/status differs")
    if set(row["sources"]) != {"official", "glama", "smithery"}:
        return outcome(
            "stale",
            "Not all three primary sources have propagated",
            sources=sorted(row["sources"]),
        )
    return outcome(
        "verified",
        "Active release discoverable across all three primary sources",
        sources=sorted(row["sources"]),
    )

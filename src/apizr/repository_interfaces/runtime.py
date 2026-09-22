"""Standalone verified repository imports. Direct execution is trusted, not isolated."""

import hashlib
import importlib
import importlib.abc
import importlib.util
import json
import os
import re
import stat
import sys
import types
from pathlib import Path, PurePosixPath
from typing import Any

from apizr.interfaces.runtime import IntegrityError, verify_binding


def digest(content: bytes) -> dict[str, str]:
    return {"algorithm": "sha256", "value": hashlib.sha256(content).hexdigest()}


def read_artifact(root: Path, name: str) -> bytes:
    path = PurePosixPath(name)
    if (
        not path.parts
        or path.is_absolute()
        or str(path) != name
        or ".." in path.parts
        or "\\" in name
    ):
        raise IntegrityError("Invalid repository artifact")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        file = os.open(
            path.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=descriptor,
        )
        with os.fdopen(file, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise IntegrityError("Repository artifact must be a regular file")
            return stream.read()
    finally:
        os.close(descriptor)


class RepositoryLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Own the local import namespace; compile only bytes just verified by digest."""

    def __init__(self, root: Path, sources: list[dict[str, Any]]) -> None:
        self.root = root
        self.sources = {s["module"]: s for s in sources}
        self.names = set(self.sources)
        for module in self.sources:
            parts = module.split(".")
            self.names.update(".".join(parts[:i]) for i in range(1, len(parts)))
        self.roots = {name.split(".")[0] for name in self.names}
        for name in self.names:
            source = self.sources.get(name)
            if (
                source
                and not source["is_package"]
                and any(n.startswith(name + ".") for n in self.names)
            ):
                raise IntegrityError("Contradictory repository import tree")
        self.installed = False

    def install(self) -> None:
        if any(name.split(".")[0] in self.roots for name in sys.modules):
            raise IntegrityError("Repository import namespace is already loaded")
        sys.meta_path.insert(0, self)
        self.installed = True

    def close(self) -> None:
        if self.installed:
            sys.meta_path.remove(self)
            for name, module in list(sys.modules.items()):
                if getattr(module, "__loader__", None) is self:
                    del sys.modules[name]
            self.installed = False

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname.split(".")[0] not in self.roots:
            return None
        if fullname not in self.names:
            raise ImportError("Local module is outside repository manifest")
        source = self.sources.get(fullname)
        return importlib.util.spec_from_loader(
            fullname, self, is_package=source is None or source["is_package"]
        )

    def create_module(self, spec: Any) -> None:
        return None

    def exec_module(self, module: types.ModuleType) -> None:
        source = self.sources.get(module.__name__)
        if source is None:
            return  # Synthetic namespace, no invented source file.
        try:
            content = read_artifact(self.root, source["bundle_path"])
            if (
                len(content) != source["size"]
                or digest(content) != source["source_digest"]
            ):
                raise IntegrityError("Repository source integrity verification failed")
            code = compile(
                content,
                "<apizr-repository:" + module.__name__ + ">",
                "exec",
                dont_inherit=True,
            )
            exec(code, module.__dict__)
        except BaseException:
            raise IntegrityError("Repository module loading failed") from None


def validate_bundle(
    root: Path, interface: str, expected: dict[str, str] | None = None
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Check every artifact and cross-artifact binding before any project import.

    Hashes establish consistency with reviewed evidence, not publisher authenticity.
    The entry point additionally pins the repository interface digest.
    """
    manifest_name = "apizr-repository-" + interface + ".json"
    manifest = json.loads(read_artifact(root, manifest_name))
    if manifest["schema_version"] != "apizr.repository-" + interface + "/v1":
        raise ValueError("schema")
    artifacts: dict[str, bytes] = {}
    for name, expected_hash in manifest["artifacts"].items():
        if name == manifest_name:
            raise ValueError("self hash")
        content = read_artifact(root, name)
        if digest(content) != expected_hash:
            raise ValueError("artifact digest")
        artifacts[name] = content
    contract = json.loads(artifacts["repository-interface.json"])
    interface_digest = digest(artifacts["repository-interface.json"])
    if interface_digest != manifest["repository_interface_digest"] or (
        expected is not None and expected != interface_digest
    ):
        raise ValueError("interface digest")
    if (
        contract["schema_version"] != "apizr.repository-interface/v1"
        or contract["interface"] != interface
    ):
        raise ValueError("interface schema")
    exposure = json.loads(artifacts["exposure-plan.json"])
    catalog = json.loads(artifacts["capability-catalog.json"])
    graph = json.loads(artifacts["capability-graph.json"])
    readiness = json.loads(artifacts["repository-readiness.json"])
    for key, name in (
        ("catalog_digest", "capability-catalog.json"),
        ("graph_digest", "capability-graph.json"),
        ("repository_readiness_digest", "repository-readiness.json"),
        ("exposure_plan_digest", "exposure-plan.json"),
    ):
        actual = digest(artifacts[name])
        if contract[key] != actual or (
            key != "exposure_plan_digest" and exposure[key] != actual
        ):
            raise ValueError("evidence binding")
    if manifest["exposure_plan_digest"] != contract["exposure_plan_digest"] or exposure[
        "exposure_policy_digest"
    ] != digest(artifacts["exposure-policy.json"]):
        raise ValueError("policy binding")
    if any(
        document["repository_digest"] != contract["repository_digest"]
        for document in (catalog, graph, readiness, exposure)
    ):
        raise ValueError("repository binding")
    if (
        interface not in exposure["interfaces"]
        or not exposure["capabilities"]
        or any(
            "direct" not in c["compatible_execution_modes"]
            for c in exposure["capabilities"]
        )
    ):
        raise ValueError("execution compatibility")
    sources = contract["sources"]
    if sources != manifest["sources"]:
        raise ValueError("source binding")
    units = {u["path"]: u for u in catalog["sources"] if u["inspection"] is not None}
    if (
        len(sources) != len(units)
        or {s["source_path"] for s in sources} != set(units)
        or len({s["module"] for s in sources}) != len(sources)
    ):
        raise ValueError("source universe")
    for source in sources:
        unit = units[source["source_path"]]
        for key in ("module", "source_digest", "size", "is_package"):
            if source[key] != unit[key]:
                raise ValueError("source evidence")
        path = (
            "source/"
            + source["module"].replace(".", "/")
            + ("/__init__.py" if source["is_package"] else ".py")
        )
        if (
            source["bundle_path"] != path
            or digest(artifacts[path]) != source["source_digest"]
            or len(artifacts[path]) != source["size"]
        ):
            raise ValueError("source artifact")
    capabilities = contract["capabilities"]
    if [c["capability_id"] for c in capabilities] != [
        c["capability_id"] for c in exposure["capabilities"]
    ]:
        raise ValueError("public surface")
    transport = manifest["endpoints" if interface == "rest" else "tools"]
    if len(transport) != len(capabilities):
        raise ValueError("transport surface")
    public_names: set[str] = set()
    for capability, invocation in zip(capabilities, transport, strict=True):
        identity = capability["capability_id"]
        if (
            identity != capability["invocation"]["capability_id"]
            or capability["module"] != identity.split(":")[1]
            or capability["public_name"] != ".".join(identity.split(":")[1:])
        ):
            raise ValueError("capability identity")
        if any(
            invocation[key] != value for key, value in capability["invocation"].items()
        ):
            raise ValueError("invocation binding")
        if interface == "rest":
            name = invocation["route"]
            if (
                name != "/capabilities/" + capability["public_name"]
                or invocation["method"] != "POST"
            ):
                raise ValueError("route")
        else:
            name = invocation["tool_name"]
            qualified = capability["public_name"]
            expected_name = (
                qualified
                if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", qualified)
                and not qualified.startswith("apizr_")
                else "apizr_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
            )
            if name != expected_name:
                raise ValueError("tool identity")
        if name in public_names:
            raise ValueError("public collision")
        public_names.add(name)
    if interface == "mcp":
        document = json.loads(artifacts["mcp-tools.json"])
        expected_tools = [
            {
                "name": tool["tool_name"],
                "inputSchema": tool["input_schema"],
                "_meta": {"sh.outerspace.apizr/capability-id": tool["capability_id"]},
                **(
                    {"description": tool["description"]}
                    if tool["description"] is not None
                    else {}
                ),
            }
            for tool in transport
        ]
        if document != {
            "schema_version": "apizr.repository-mcp/v1",
            "protocol": {"target": manifest["protocol"]["target"]},
            "tools": expected_tools,
        }:
            raise ValueError("tool document binding")
    return manifest, artifacts


def load_bundle(
    root: Path, interface: str, expected: dict[str, str] | None = None
) -> tuple[
    dict[str, Any], dict[str, types.FunctionType], RepositoryLoader, dict[str, bytes]
]:
    loader = None
    try:
        manifest, artifacts = validate_bundle(root, interface, expected)
        loader = RepositoryLoader(root, manifest["sources"])
        loader.install()
        bindings: dict[str, types.FunctionType] = {}
        for invocation in manifest["endpoints" if interface == "rest" else "tools"]:
            identity = invocation["capability_id"]
            module = importlib.import_module(identity.split(":")[1])
            bindings[identity] = verify_binding(module, invocation)
        return manifest, bindings, loader, artifacts
    except BaseException:
        if loader is not None:
            loader.close()
        raise IntegrityError("Repository bundle startup failed") from None

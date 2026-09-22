"""Opt-in strict bridge files, leaving all existing allow bundle bytes untouched."""

from apizr.governed.embedding import source


def strict_files(
    artifacts: dict[str, bytes], *, repository: bool = False
) -> dict[str, bytes]:
    artifacts = dict(artifacts)
    module = "repository" if repository else "single"
    for name in ("__init__", "provider", module):
        path = f"subprocess_guard/{name}.py"
        content = source(path)
        artifacts["apizr_governed/" + path] = content.replace(
            "from apizr.", "from apizr_governed."
        ).encode()
    target = "governed_repository" if repository else "governed_oci"
    path = "apizr_governed/" + target + "/runtime.py"
    text = artifacts[path].decode()
    if repository:
        text = (
            text.replace(
                "from apizr_governed.repository_execution.planner import evidence, validate_plan, validate_sources",
                "from apizr_governed.subprocess_guard.repository import evidence, validate_plan, validate_sources",
            )
            .replace(
                "from apizr_governed.repository_execution.supervisor import execute",
                "from apizr_governed.subprocess_guard.repository import execute",
            )
            .replace(
                "from apizr_governed.repository_execution.docker import RepositoryDockerProvider",
                "from apizr_governed.subprocess_guard.repository import DenyRepositoryProvider as RepositoryDockerProvider",
            )
        )
    else:
        text = (
            text.replace(
                "from apizr_governed.oci.planner import validate_plan",
                "from apizr_governed.subprocess_guard.single import validate_plan",
            )
            .replace(
                "from apizr_governed.oci.supervisor import execute",
                "from apizr_governed.subprocess_guard.single import execute",
            )
            .replace(
                "from apizr_governed.oci.docker import DockerProvider",
                "from apizr_governed.subprocess_guard.provider import DenyDockerProvider as DockerProvider",
            )
        )
    artifacts[path] = text.encode()
    return artifacts

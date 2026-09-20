"""Render a deterministic REST bundle without importing or executing its source."""

from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from apizr.capabilities import canonical_bytes as ir_bytes
from apizr.capabilities.model import Digest
from apizr.inspection import Inspection
from apizr.readiness import canonical_bytes as readiness_bytes

from .model import Manifest
from .output import write_bundle
from .planner import plan
from .rendering import runtime_source
from .schema import openapi
from .serialization import json_bytes

REQUIREMENTS = b"fastapi>=0.141,<1\nstarlette>=1.3.1\nuvicorn>=0.30,<1\n"


def render(
    inspection: Inspection,
    source: bytes,
    *,
    executable: bytes | None = None,
    select: Sequence[str] | None = None,
) -> dict[str, bytes]:
    rest = plan(inspection, source, executable=executable, select=select)
    executable = (
        source if inspection.capability_ir.source.kind == "python" else executable
    )
    if executable is None:
        raise ValueError("Notebook executable bytes are required")
    template = runtime_source()
    adapter = template + (
        "\n\nROOT = Path(__file__).resolve().parent\n"
        'MANIFEST = json.loads((ROOT / "apizr-rest.json").read_bytes())\n'
        'PLAN = {**MANIFEST, "endpoints": MANIFEST["capabilities"]}\n'
        "app = create_app(ROOT, PLAN)\n"
    )
    artifacts = {
        "app.py": adapter.encode("utf-8"),
        rest.executable_path: executable,
        "capability-ir.json": ir_bytes(inspection.capability_ir),
        "readiness.json": readiness_bytes(inspection.readiness),
        "openapi.json": json_bytes(openapi(rest.endpoints)),
        "requirements.txt": REQUIREMENTS,
    }
    for parent in PurePosixPath(rest.executable_path).parents:
        if parent.as_posix() not in (".", "source"):
            artifacts.setdefault(parent.as_posix() + "/__init__.py", b"")
    if inspection.capability_ir.source.kind == "notebook":
        artifacts["notebook.ipynb"] = source
    manifest = Manifest(
        source=rest.source,
        executable_digest=rest.executable_digest,
        executable_path=rest.executable_path,
        ir_digest=rest.ir_digest,
        readiness_digest=rest.readiness_digest,
        capabilities=rest.endpoints,
        artifacts={
            name: Digest.of_bytes(content)
            for name, content in sorted(artifacts.items())
        },
    )
    artifacts["apizr-rest.json"] = json_bytes(manifest.model_dump(mode="json"))
    return dict(sorted(artifacts.items()))


def generate(
    inspection: Inspection,
    source: bytes,
    output: str | Path,
    *,
    executable: bytes | None = None,
    select: Sequence[str] | None = None,
) -> tuple[str, ...]:
    artifacts = render(inspection, source, executable=executable, select=select)
    write_bundle(output, artifacts)
    return tuple(artifacts)

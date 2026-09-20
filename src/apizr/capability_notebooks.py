"""Notebook adapter outside the framework-independent capability core."""

import io
from pathlib import Path

from apizr.capabilities import CapabilityDocument, inspect_source
from apizr.capabilities.model import Digest, Source
from apizr.modules.notebook_transformr.transformr.nbTransformr import NotebookTransformr


def inspect_notebook(path: str | Path, *, module_name: str) -> CapabilityDocument:
    """Hash original notebook bytes and the exact non-executed exported Python."""
    raw = Path(path).read_bytes()
    python_source, _ = NotebookTransformr().convert_notebook(io.BytesIO(raw))
    analyzed = inspect_source(python_source, module_name=module_name)
    return CapabilityDocument(
        source=Source(
            kind="notebook",
            module=analyzed.source.module,
            digest=Digest.of_bytes(raw),
            transformed_digest=analyzed.source.digest,
        ),
        capabilities=analyzed.capabilities,
        diagnostics=analyzed.diagnostics,
    )

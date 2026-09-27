"""Build catalog entries from existing declarations and inspected local wheels."""

import hashlib
import tempfile
from importlib.metadata import version
from pathlib import Path

from apizr.config_files import read_regular
from apizr.local_plugins import locking
from apizr.local_plugins.wheel import MAX_WHEEL_BYTES
from apizr.plugin_lock import LockError, ProjectLock, create_lock
from apizr.plugin_lock.models import Requirements, Wheel

from .models import (
    Artifact,
    CatalogError,
    Compatibility,
    Entry,
    Prerequisite,
    Provenance,
)


def generate_entries(
    project: Path,
    wheelhouse: Path,
    *,
    descriptions: dict[str, str],
    provenance: Provenance,
    prerequisites: dict[str, tuple[Prerequisite, ...]] | None = None,
) -> tuple[Entry, ...]:
    """Inspect real artifacts using the lock creator. Requirements in wheelhouse
    must already be at requirements/NAME.lock and match the declared project.
    No build, downloads, import or installation takes place in this operation.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="apizr-catalog-generate-") as temporary:
            path = Path(temporary) / "lock.json"
            result = create_lock(project, wheelhouse, path)
            if not result.valid:
                raise CatalogError("catalog_artifacts_invalid")
            lock = ProjectLock.model_validate_json(path.read_bytes(), strict=True)

        def artifact(wheel: Wheel) -> Artifact:
            raw = read_regular(wheelhouse / wheel.filename, MAX_WHEEL_BYTES)
            if hashlib.sha256(raw).hexdigest() != wheel.sha256:
                raise CatalogError("wheel_mismatch")
            return Artifact(**wheel.model_dump(), size=len(raw))

        entries = []
        for plugin in lock.plugins:
            requirements = None
            if plugin.requirements:
                requirements = Requirements(
                    path=f"requirements/{plugin.wheel.name}.lock",
                    source_sha256=plugin.requirements.source_sha256,
                )
                raw = read_regular(
                    wheelhouse / requirements.path, locking.MAX_LOCK_BYTES
                )
                if hashlib.sha256(raw).hexdigest() != requirements.source_sha256:
                    raise CatalogError("requirements_mismatch")
            entries.append(
                Entry(
                    description=descriptions[plugin.wheel.name],
                    manifest=plugin.manifest,
                    wheel=artifact(plugin.wheel),
                    dependencies=tuple(artifact(w) for w in plugin.dependencies),
                    requirements=requirements,
                    compatibility=Compatibility(
                        apizr_version=version("outerspace-apizr"),
                        channel=provenance.status,
                        target=lock.target,
                    ),
                    provenance=provenance,
                    prerequisites=(prerequisites or {}).get(plugin.wheel.name, ()),
                )
            )
        return tuple(entries)
    except (OSError, ValueError, KeyError, LockError):
        raise CatalogError("catalog_generation_failed") from None

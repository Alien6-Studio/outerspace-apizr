"""Read a bounded wheel snapshot and its declarative metadata, never import it."""

import hashlib
import io
import json
import re
import stat
import zipfile
import zlib
from email import policy
from email.parser import Parser
from pathlib import Path, PurePosixPath

from apizr.extension_runtime.protocol import unique_object

from .models import LockedDistribution, Manifest, PluginError, canonical_name

MAX_WHEEL_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_METADATA_BYTES = 65536
MANIFEST = "apizr-extension.json"


def metadata_headers(raw: bytes) -> str:
    """Bound identity/dependency headers, not the unused PyPI description body.

    Callers read at most MAX_METADATA_BYTES + 1 bytes, even for large METADATA.
    No declaration after the RFC-style blank line is a metadata header.
    """
    headers = re.split(b"\r?\n\r?\n", raw, maxsplit=1)[0]
    if len(headers) > MAX_METADATA_BYTES:
        raise PluginError("metadata_too_large")
    return headers.decode("utf-8") + "\n\n"


def inspect_wheel(
    path: Path, sha256: str, *, allow_dependencies: bool = False
) -> tuple[bytes, Manifest]:
    data, metadata = _inspect(
        path, sha256, plugin=True, allow_dependencies=allow_dependencies
    )
    assert isinstance(metadata, Manifest)
    return data, metadata


def inspect_dependency(path: Path, sha256: str) -> tuple[bytes, LockedDistribution]:
    data, metadata = _inspect(path, sha256, plugin=False, allow_dependencies=True)
    assert isinstance(metadata, LockedDistribution)
    return data, metadata


def _inspect(
    path: Path, sha256: str, *, plugin: bool, allow_dependencies: bool
) -> tuple[bytes, Manifest | LockedDistribution]:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        raise PluginError("invalid_sha256")
    if path.suffix != ".whl":
        raise PluginError("local_wheel_required")
    try:
        # O_NONBLOCK avoids hanging on a FIFO disguised as a wheel.
        import os

        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise PluginError("local_wheel_required")
            data = source.read(MAX_WHEEL_BYTES + 1)
        if len(data) > MAX_WHEEL_BYTES:
            raise PluginError("wheel_too_large")
        if hashlib.sha256(data).hexdigest() != sha256.lower():
            raise PluginError("hash_mismatch")
        return data, _manifest(
            data, path.name, sha256.lower(), plugin, allow_dependencies
        )
    except (
        OSError,
        ValueError,
        KeyError,
        zipfile.BadZipFile,
        RuntimeError,
        EOFError,
        zlib.error,
    ):
        raise PluginError("invalid_wheel") from None


def _manifest(
    data: bytes, filename: str, digest: str, plugin: bool, allow_dependencies: bool
) -> Manifest | LockedDistribution:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if (
            len(names) > 10000
            or len({name.casefold() for name in names}) != len(names)
            or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES
        ):
            raise PluginError("invalid_wheel")
        for entry in entries:
            parts = PurePosixPath(entry.filename).parts
            kind = stat.S_IFMT(entry.external_attr >> 16)
            if (
                not parts
                or entry.filename.startswith("/")
                or ".." in parts
                or "\\" in entry.filename
                or PurePosixPath(entry.filename).as_posix()
                != entry.filename.rstrip("/")
                or kind not in (0, stat.S_IFREG, stat.S_IFDIR)
                or entry.flag_bits & 1
                or entry.filename.lower().endswith(".pth")
                or any(
                    part.lower().split(".", 1)[0] in ("sitecustomize", "usercustomize")
                    for part in parts
                )
            ):
                raise PluginError("unsupported_wheel_layout")

        def read(name: str) -> str:
            entry = archive.getinfo(name)
            if name.endswith(".dist-info/METADATA"):
                with archive.open(entry) as stream:
                    return metadata_headers(stream.read(MAX_METADATA_BYTES + 1))
            if entry.file_size > MAX_METADATA_BYTES:
                raise PluginError("metadata_too_large")
            return archive.read(entry).decode("utf-8")

        metadata_paths = [
            name for name in names if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1 or metadata_paths[0].count("/") != 1:
            raise PluginError("invalid_wheel")
        metadata = Parser(policy=policy.default).parsestr(read(metadata_paths[0]))
        if metadata.defects or any(
            len(metadata.get_all(key, [])) != 1
            for key in ("Name", "Version", "Metadata-Version")
        ):
            raise PluginError("invalid_wheel")
        if metadata.get_all("Requires-Dist") and not allow_dependencies:
            # The original single-wheel path remains dependency-free.
            raise PluginError("dependencies_not_supported")
        # No direct references from wheel metadata either: dependencies must be
        # resolved exclusively from the verified local snapshot.
        if allow_dependencies and any(
            "@" in value for value in metadata.get_all("Requires-Dist", [])
        ):
            raise PluginError("unsupported_dependency_reference")
        identity = LockedDistribution(
            name=canonical_name(str(metadata["Name"])),
            version=str(metadata["Version"]),
            sha256=digest,
        )
        components = filename.removesuffix(".whl").split("-")
        dist_info = metadata_paths[0].split("/")[0]
        if (
            len(components) not in (5, 6)
            or canonical_name(components[0]) != identity.name
            or components[1] != identity.version
            or dist_info != f"{components[0]}-{components[1]}.dist-info"
        ):
            raise PluginError("inconsistent_metadata")
        wheel = Parser(policy=policy.default).parsestr(read(dist_info + "/WHEEL"))
        if wheel.get("Wheel-Version") != "1.0" or dist_info + "/RECORD" not in names:
            raise PluginError("unsupported_wheel_layout")
        if not plugin:
            return identity
        try:
            manifest = Manifest.model_validate(
                json.loads(read(MANIFEST), object_pairs_hook=unique_object), strict=True
            )
        except (ValueError, KeyError, RecursionError):
            raise PluginError("invalid_manifest") from None
        if (manifest.name, manifest.version) != (identity.name, identity.version):
            raise PluginError("inconsistent_metadata")
        entry = manifest.module.replace(".", "/")
        if entry + ".py" not in names and entry + "/__main__.py" not in names:
            raise PluginError("missing_entry_module")
        return manifest

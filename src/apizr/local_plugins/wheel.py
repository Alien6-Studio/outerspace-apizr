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

from .models import Manifest, PluginError, canonical_name

MAX_WHEEL_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_METADATA_BYTES = 65536
MANIFEST = "apizr-extension.json"


def inspect_wheel(path: Path, sha256: str) -> tuple[bytes, Manifest]:
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
        return data, _manifest(data, path.name)
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


def _manifest(data: bytes, filename: str) -> Manifest:
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
                or entry.filename.endswith(".pth")
                or parts[-1] in ("sitecustomize.py", "usercustomize.py")
            ):
                raise PluginError("unsupported_wheel_layout")

        def read(name: str) -> str:
            entry = archive.getinfo(name)
            if entry.file_size > MAX_METADATA_BYTES:
                raise PluginError("metadata_too_large")
            return archive.read(entry).decode("utf-8")

        try:
            manifest = Manifest.model_validate(
                json.loads(read(MANIFEST), object_pairs_hook=unique_object), strict=True
            )
        except (ValueError, KeyError, RecursionError):
            raise PluginError("invalid_manifest") from None
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
        if metadata.get_all("Requires-Dist"):
            # Even conditional/extra dependencies are outside this iteration.
            raise PluginError("dependencies_not_supported")
        components = filename.removesuffix(".whl").split("-")
        dist_info = metadata_paths[0].split("/")[0]
        if (
            len(components) not in (5, 6)
            or canonical_name(str(metadata["Name"])) != manifest.name
            or str(metadata["Version"]) != manifest.version
            or canonical_name(components[0]) != manifest.name
            or components[1] != manifest.version
            or dist_info != f"{components[0]}-{components[1]}.dist-info"
        ):
            raise PluginError("inconsistent_metadata")
        wheel = Parser(policy=policy.default).parsestr(read(dist_info + "/WHEEL"))
        if wheel.get("Wheel-Version") != "1.0" or dist_info + "/RECORD" not in names:
            raise PluginError("unsupported_wheel_layout")
        entry = manifest.module.replace(".", "/")
        if entry + ".py" not in names and entry + "/__main__.py" not in names:
            raise PluginError("missing_entry_module")
        return manifest

"""Shared upload validation for the local generation service."""

from pathlib import PurePosixPath, PureWindowsPath

from fastapi import HTTPException, UploadFile

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def read_upload(file: UploadFile, extensions):
    name = file.filename or ""
    if (
        not name
        or PurePosixPath(name).name != name
        or PureWindowsPath(name).name != name
        or name in {".", ".."}
    ):
        raise HTTPException(400, "Expected a filename without directory components")
    if PurePosixPath(name).suffix not in extensions:
        raise HTTPException(
            400, f"Supported extensions: {', '.join(sorted(extensions))}"
        )
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the 10 MiB limit")
    return name, data

"""Conservative current-host wheel tags; uv still validates installation.

Support the native wheels used by official plugins without importing optional
packaging or enumerating a dependency resolver. Unknown platform tags fail closed.
"""

import os
import re

from .models import Target


def platform_matches(tag: str, target: Target) -> bool:
    if tag in ("any", target.platform.replace("-", "_").replace(".", "_")):
        return True
    mac = re.fullmatch(r"macosx_(\d+)_(\d+)_(arm64|x86_64|universal2)", tag)
    host = re.fullmatch(r"macosx-(\d+)\.(\d+)-(arm64|x86_64)", target.platform)
    if mac and host:
        return (int(mac[1]), int(mac[2])) <= (int(host[1]), int(host[2])) and mac[
            3
        ] in (host[3], "universal2")
    linux = re.fullmatch(r"manylinux_(\d+)_(\d+)_(x86_64|aarch64)", tag)
    if linux and target.platform == "linux-" + linux[3] and target.machine == linux[3]:
        try:
            libc = os.confstr("CS_GNU_LIBC_VERSION") or ""
        except (ValueError, OSError):
            return False
        match = re.fullmatch(r"glibc (\d+)\.(\d+)", libc)
        return bool(
            match and (int(linux[1]), int(linux[2])) <= (int(match[1]), int(match[2]))
        )
    return False


def wheel_matches(filename: str, target: Target) -> bool:
    python, abi, platform = filename[:-4].rsplit("-", 3)[-3:]
    major, minor, _ = target.python.split(".")
    tags = {"py" + major, "py" + major + minor}
    abis = {"none"}
    if target.implementation == "cpython":
        tags.add("cp" + major + minor)
        threaded = "t-" in target.abi
        abis.add("cp" + major + minor + ("t" if threaded else ""))
        # Stable ABI wheels apply to CPython >= their minimum, excluding free-threaded.
        if abi == "abi3" and not threaded:
            abis.add("abi3")
            tags.update("cp3" + str(v) for v in range(2, int(minor) + 1))
    return bool(
        tags.intersection(python.split("."))
        and abis.intersection(abi.split("."))
        and any(platform_matches(p, target) for p in platform.split("."))
    )

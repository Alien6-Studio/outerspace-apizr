"""Bound ZIP metadata before ZipFile allocates a ZipInfo for every entry."""

import struct

from .models import PluginError

MAX_ENTRIES = 10_000


def preflight_directory(data: bytes) -> None:
    """Scan actual central records, including fixed ZIP64 and prepended archives.

    Wheel admission does not support multi-disk ZIPs or ZIP64 extensible data.
    Count fields alone are insufficient: ZipFile iterates the directory's bytes.
    No filenames, extra fields or per-entry objects are materialized here.
    """
    end = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if end < 0 or end + 22 > len(data):
        raise PluginError("invalid_wheel")
    _, disk, start_disk, count_disk, count, size, offset, comment = struct.unpack_from(
        "<4s4H2IH", data, end
    )
    if end + 22 + comment != len(data):
        raise PluginError("invalid_wheel")
    directory_end = end
    if end >= 20 and data[end - 20 : end - 16] == b"PK\x06\x07":
        _, locator_disk, location, disks = struct.unpack_from("<4sIQI", data, end - 20)
        directory_end = end - 76
        if (
            directory_end < 0
            or location > directory_end
            or (
                location != directory_end
                and data[location : location + 4] == b"PK\x06\x06"
            )
        ):
            # Python versions supporting extensible ZIP64 prefer a valid record
            # at the locator's offset over the fixed record immediately before
            # it. Refuse that ambiguity rather than preflight a different index.
            raise PluginError("invalid_wheel")
        (
            signature,
            record_size,
            _,
            _,
            disk,
            start_disk,
            count_disk,
            count,
            size,
            offset,
        ) = struct.unpack_from("<4sQ2H2I4Q", data, directory_end)
        if (
            signature != b"PK\x06\x06"
            or record_size != 44
            or locator_disk != 0
            or disks != 1
            or offset + size != location
        ):
            raise PluginError("invalid_wheel")
    if disk != 0 or start_disk != 0 or count_disk != count or count > MAX_ENTRIES:
        raise PluginError("invalid_wheel")
    start = directory_end - size
    if start < 0 or offset > start:
        raise PluginError("invalid_wheel")
    position = start
    actual = 0
    while position < directory_end:
        if (
            position + 46 > directory_end
            or data[position : position + 4] != b"PK\x01\x02"
        ):
            raise PluginError("invalid_wheel")
        name, extra, comment = struct.unpack_from("<3H", data, position + 28)
        position += 46 + name + extra + comment
        actual += 1
        if actual > MAX_ENTRIES or position > directory_end:
            raise PluginError("invalid_wheel")
    if actual != count:
        raise PluginError("invalid_wheel")

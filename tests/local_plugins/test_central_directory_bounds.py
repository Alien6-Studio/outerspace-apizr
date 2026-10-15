"""Reject amplified ZIP metadata before the standard library builds its index."""

import io
import struct
import zipfile

import pytest

from apizr.plugins.artifacts import wheel
from apizr.plugins.artifacts.central_directory import MAX_ENTRIES, preflight_directory
from apizr.plugins.artifacts.models import PluginError


def forbidden(*args, **kwargs):
    raise AssertionError("ZIP index allocated before admission")


def directory_archive(count):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index in range(count):
            archive.writestr(str(index), b"")
    return buffer.getvalue()


@pytest.mark.parametrize("advertised", [0, 1, MAX_ENTRIES, MAX_ENTRIES + 1])
def test_entry_budget_precedes_zipfile_even_with_forged_counts(monkeypatch, advertised):
    raw = bytearray(directory_archive(MAX_ENTRIES + 1))
    struct.pack_into("<2H", raw, len(raw) - 14, advertised, advertised)
    monkeypatch.setattr(wheel.zipfile, "ZipFile", forbidden)
    with pytest.raises(PluginError, match="invalid_wheel"):
        wheel.inspect_dependency_bytes(bytes(raw), "probe-1-py3-none-any.whl")


def zip64(raw):
    end = len(raw) - 22
    _, _, _, count, _, size, offset, _ = struct.unpack_from("<4s4H2IH", raw, end)
    extended = struct.pack(
        "<4sQ2H2I4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, count, count, size, offset
    )
    locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, end, 1)
    classic = struct.pack(
        "<4s4H2IH", b"PK\x05\x06", 0, 0, 65535, 65535, 0xFFFFFFFF, 0xFFFFFFFF, 0
    )
    return raw[:end] + extended + locator + classic


@pytest.mark.parametrize("extended", [False, True])
@pytest.mark.parametrize("prefix", [b"", b"executable prefix\n"])
def test_real_wheels_keep_zip64_prefix_and_comment_support(
    wheel_factory, extended, prefix
):
    path, _ = wheel_factory(plugin=False, files={"probe.py": b"answer = 42\n"})
    raw = path.read_bytes()
    if extended:
        raw = zip64(raw)
    raw = prefix + raw
    raw = raw[:-2] + struct.pack("<H", 7) + b"comment"
    assert wheel.inspect_dependency_bytes(raw, path.name).name == "local-probe"


@pytest.mark.parametrize(
    "change",
    ["truncated", "extra", "offset", "disk", "count", "signature", "length", "comment"],
)
def test_inconsistent_directory_records_are_refused(change):
    raw = bytearray(directory_archive(1))
    end = len(raw) - 22
    central = raw.index(b"PK\x01\x02")
    if change == "truncated":
        raw = raw[:-1]
    elif change == "extra":
        raw = bytearray(b"not a zip")
    elif change == "offset":
        struct.pack_into("<I", raw, end + 16, len(raw))
    elif change == "disk":
        struct.pack_into("<H", raw, end + 4, 1)
    elif change == "count":
        struct.pack_into("<2H", raw, end + 8, 0, 0)
    elif change == "signature":
        raw[central] = 0
    elif change == "length":
        struct.pack_into("<H", raw, central + 28, 65535)
    elif change == "comment":
        struct.pack_into("<H", raw, end + 20, 3)
    with pytest.raises(PluginError, match="invalid_wheel"):
        preflight_directory(bytes(raw))


@pytest.mark.parametrize("field, value", [(4, 45), (16, 1), (20, 1), (48, 999999)])
def test_zip64_layout_is_checked(field, value):
    raw = bytearray(zip64(directory_archive(1)))
    position = raw.index(b"PK\x06\x06")
    struct.pack_into("<I", raw, position + field, value)
    with pytest.raises(PluginError, match="invalid_wheel"):
        preflight_directory(bytes(raw))


def test_exact_existing_entry_limit_is_admitted():
    preflight_directory(directory_archive(MAX_ENTRIES))


def test_zip64_locator_cannot_point_beyond_its_record():
    raw = bytearray(zip64(directory_archive(1)))
    position = raw.index(b"PK\x06\x07")
    struct.pack_into("<Q", raw, position + 8, len(raw))
    with pytest.raises(PluginError, match="invalid_wheel"):
        preflight_directory(bytes(raw))


def test_zip64_extensible_record_cannot_hide_a_second_directory(monkeypatch):
    raw = directory_archive(MAX_ENTRIES + 1)
    end = len(raw) - 22
    _, _, _, count, _, size, offset, _ = struct.unpack_from("<4s4H2IH", raw, end)
    small = directory_archive(1)
    fake_directory = small[small.index(b"PK\x01\x02") : -22]
    fake_end = struct.pack(
        "<4sQ2H2I4Q",
        b"PK\x06\x06",
        44,
        45,
        45,
        0,
        0,
        1,
        1,
        len(fake_directory),
        end - len(fake_directory),
    )
    extension = fake_directory + fake_end
    real_end = struct.pack(
        "<4sQ2H2I4Q",
        b"PK\x06\x06",
        44 + len(extension),
        45,
        45,
        0,
        0,
        count,
        count,
        size,
        offset,
    )
    locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, end, 1)
    classic = struct.pack(
        "<4s4H2IH", b"PK\x05\x06", 0, 0, 65535, 65535, 0xFFFFFFFF, 0xFFFFFFFF, 0
    )
    forged = raw[:end] + real_end + extension + locator + classic
    monkeypatch.setattr(wheel.zipfile, "ZipFile", forbidden)
    with pytest.raises(PluginError, match="invalid_wheel"):
        wheel.inspect_dependency_bytes(forged, "probe-1-py3-none-any.whl")

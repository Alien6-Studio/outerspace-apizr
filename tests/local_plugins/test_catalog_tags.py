"""Only native tag families needed by the official wheel closures are admitted."""

import pytest

from apizr.plugin_lock.models import Target
from apizr.plugin_lock.tags import platform_matches, wheel_matches

MAC = Target(
    implementation="cpython",
    python="3.14.0",
    platform="macosx-14.0-arm64",
    machine="arm64",
    abi="cpython-314-darwin",
)
LINUX = Target(
    implementation="cpython",
    python="3.11.9",
    platform="linux-x86_64",
    machine="x86_64",
    abi="cpython-311-x86_64-linux-gnu",
)


@pytest.mark.parametrize(
    "tag,valid",
    [
        ("cp314-cp314-macosx_11_0_arm64", True),
        ("cp311-abi3-macosx_11_0_universal2", True),
        ("cp315-abi3-macosx_11_0_arm64", False),
        ("cp314-cp314-macosx_26_0_arm64", False),
        ("cp314-cp314-macosx_11_0_x86_64", False),
        ("py3-none-any", True),
        ("py2-none-any", False),
        ("cp311-cp311-macosx_11_0_arm64", False),
    ],
)
def test_mac(tag, valid):
    assert wheel_matches("x-1-" + tag + ".whl", MAC) == valid


def test_abi3_does_not_allow_free_threaded():
    assert not wheel_matches(
        "x-1-cp311-abi3-macosx_11_0_arm64.whl",
        MAC.model_copy(update={"abi": "cpython-314t-darwin"}),
    )


@pytest.mark.parametrize(
    "libc,tag,valid",
    [
        ("glibc 2.39", "manylinux_2_28_x86_64", True),
        ("glibc 2.17", "manylinux_2_28_x86_64", False),
        ("glibc 2.39", "manylinux_2_28_aarch64", False),
        ("musl 1.2", "manylinux_2_28_x86_64", False),
        (None, "manylinux_2_28_x86_64", False),
        ("glibc 2.39", "musllinux_1_2_x86_64", False),
    ],
)
def test_linux(monkeypatch, libc, tag, valid):
    monkeypatch.setattr("os.confstr", lambda key: libc)
    assert platform_matches(tag, LINUX) == valid


def test_unknown_libc(monkeypatch):
    def unavailable(key):
        raise ValueError()

    monkeypatch.setattr("os.confstr", unavailable)
    assert not platform_matches("manylinux_2_28_x86_64", LINUX)


@pytest.mark.parametrize("build", ["macosx-10.9-universal2", "macosx-11.0-arm64"])
@pytest.mark.parametrize("release", ["26.0.0", "11.0.0"])
def test_macos_running_os_and_active_universal_slice(monkeypatch, build, release):
    from apizr.plugin_lock import tags

    target = MAC.model_copy(
        update={"python": "3.11.9", "platform": build, "abi": "cpython-311-darwin"}
    )
    monkeypatch.setattr(tags, "current_target", lambda: target)
    monkeypatch.setattr(tags.sys, "platform", "darwin")
    monkeypatch.setattr(tags.platform, "mac_ver", lambda: (release, (), "arm64"))
    assert wheel_matches("p-1-cp311-cp311-macosx_11_0_arm64.whl", target)
    assert wheel_matches("p-1-cp311-cp311-macosx_10_9_universal2.whl", target)
    assert not wheel_matches("p-1-cp311-cp311-macosx_11_0_x86_64.whl", target)
    assert not wheel_matches("p-1-cp311-cp311-macosx_99_0_arm64.whl", target)


def test_macos_unknown_runtime_stays_conservative(monkeypatch):
    from apizr.plugin_lock import tags

    target = MAC.model_copy(update={"platform": "macosx-10.9-universal2"})
    monkeypatch.setattr(tags, "current_target", lambda: target)
    monkeypatch.setattr(tags.sys, "platform", "darwin")
    monkeypatch.setattr(tags.platform, "mac_ver", lambda: ("", (), "arm64"))
    assert not platform_matches("macosx_11_0_arm64", target)

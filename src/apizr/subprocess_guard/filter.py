"""Install an irreversible, native-ABI seccomp filter before project imports.

This restricts process/thread creation and image replacement, not arbitrary code
execution or all kernel interactions. The Docker isolation profile still applies.
"""

import ctypes
import errno
import platform
import sys
from pathlib import Path

# Linux UAPI: audit.h, filter.h, seccomp.h and the native syscall tables.
# No compatibility ABI is admitted.
ARCHITECTURES = {
    "x86_64": (0xC000003E, {56, 57, 58, 59, 101, 322, 425, 426, 427, 435}),
    "aarch64": (0xC00000B7, {117, 220, 221, 281, 425, 426, 427, 435}),
}
# Syscalls >= 512 include x32 aliases and are refused.
# Both native tables currently assign process creation below this bound.
SYSCALL_BOUND = 512
DENIED = 0x00050000 | errno.EPERM
ALLOW = 0x7FFF0000
KILL = 0x80000000


class Instruction(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint32),
    ]


class Program(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Instruction))]


def instructions(machine: str) -> list[tuple[int, int, int, int]]:
    if machine not in ARCHITECTURES:
        raise RuntimeError("Unsupported subprocess-deny architecture")
    arch, forbidden = ARCHITECTURES[machine]
    result = [
        (0x20, 0, 0, 4),  # Load seccomp_data.arch.
        (0x15, 1, 0, arch),
        (0x06, 0, 0, KILL),
        (0x20, 0, 0, 0),  # Load seccomp_data.nr.
        (0x35, 0, 1, SYSCALL_BOUND),  # JGE; includes x32 and negative numbers.
        (0x06, 0, 0, DENIED),
    ]
    for number in sorted(forbidden):
        result.extend([(0x15, 0, 1, number), (0x06, 0, 0, DENIED)])
    result.append((0x06, 0, 0, ALLOW))
    return result


def install() -> None:
    if (
        sys.platform != "linux"
        or ctypes.sizeof(ctypes.c_void_p) != 8
        or sys.byteorder != "little"
    ):
        raise RuntimeError("Subprocess deny requires native 64-bit Linux")
    code = instructions(platform.machine())
    # prctl attaches to the calling thread. Refuse any pre-existing sibling that
    # could remain outside the filter. No application module has been imported.
    if len(list(Path("/proc/self/task").iterdir())) != 1:
        raise RuntimeError("Subprocess deny requires a single-threaded worker")
    libc = ctypes.CDLL(None, use_errno=True)
    array = (Instruction * len(code))(*(Instruction(*item) for item in code))
    program = Program(len(code), array)
    # Explicit argument types avoid variadic integer/pointer width conversion.
    prctl = libc.prctl
    prctl.restype = ctypes.c_int
    prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    if prctl(38, 1, 0, 0, 0) != 0 or prctl(39, 0, 0, 0, 0) != 1:
        raise RuntimeError("Unable to set no-new-privileges")
    if prctl(22, 2, ctypes.addressof(program), 0, 0) != 0 or prctl(21, 0, 0, 0, 0) != 2:
        raise RuntimeError("Unable to install subprocess-deny filter")

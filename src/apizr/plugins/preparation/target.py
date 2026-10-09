"""Measure an explicit native interpreter; never infer a target from PATH."""

import json
import os
import platform as host_platform
import re
import sys
from dataclasses import dataclass
from itertools import chain, islice
from pathlib import Path

from apizr.environment.python_target import validate_python_target
from apizr.plugins.lock.models import Target

from .models import Control, PreparationError
from .process import run

PROGRAM = """import json, os, platform, sys, sysconfig
machine = platform.machine()
target_platform = sysconfig.get_platform()
if sys.platform == 'darwin':
    release = platform.mac_ver()[0].split('.')
    target_platform = 'macosx-' + '.'.join(release[:2]) + '-' + machine
print(json.dumps({'target': {'implementation': sys.implementation.name,
'python': platform.python_version(), 'platform': target_platform,
'machine': machine, 'abi': str(sysconfig.get_config_var('SOABI') or '')},
'system': sys.platform, 'libc': platform.libc_ver()}))
"""


@dataclass(frozen=True)
class NativeTarget:
    identity: Target
    resolver_platform: str
    environment: dict[str, str]


def probe(python: Path, platform: str, work: Path, control: Control) -> NativeTarget:
    if (
        not python.is_absolute()
        or not python.is_file()
        or not os.access(python, os.X_OK)
    ):
        raise PreparationError("interpreter_unavailable")
    try:
        result = run(
            [str(python), "-I", "-S", "-B", "-u", "-c", PROGRAM],
            work,
            control,
            max_stdout=8192,
        )
        if result.code:
            raise PreparationError("interpreter_unavailable")
        data = json.loads(result.stdout)
        target = Target.model_validate(data["target"], strict=True)
        major, minor, _ = map(int, target.python.split("."))
        validate_python_target((major, minor))
        if target.implementation != "cpython" or not target.abi:
            raise ValueError()
        environment: dict[str, str] = {}
        if data["system"] == "darwin" and target.machine in {"arm64", "x86_64"}:
            match = re.fullmatch(r"macosx-(\d+\.\d+)-(arm64|x86_64)", target.platform)
            if match is None or match[2] != target.machine:
                raise ValueError()
            resolver_platform = (
                "aarch64" if target.machine == "arm64" else "x86_64"
            ) + "-apple-darwin"
            environment["MACOSX_DEPLOYMENT_TARGET"] = match[1]
        elif data["system"] == "linux" and target.machine in {"x86_64", "aarch64"}:
            libc, version = data["libc"]
            match = re.fullmatch(r"2\.(\d+)", version)
            if (
                libc != "glibc"
                or match is None
                or int(match[1]) not in {17, 28, *range(31, 41)}
            ):
                raise ValueError()
            resolver_platform = f"{target.machine}-manylinux_2_{match[1]}"
        else:
            raise ValueError()
        if platform not in {"native", target.platform, resolver_platform}:
            raise ValueError()
        return NativeTarget(target, resolver_platform, environment)
    except (ValueError, KeyError, TypeError, RecursionError):
        raise PreparationError("target_invalid") from None


def supported_tags(target: Target) -> dict[str, int]:
    """PyPA preference order for the measured interpreter, never the parent ABI."""
    try:
        from packaging.tags import (
            compatible_tags,
            cpython_tags,
            mac_platforms,
            platform_tags,
        )
    except ImportError:
        raise PreparationError("preparation_extra_required") from None
    major, minor, _ = map(int, target.python.split("."))
    interpreter = f"cp{major}{minor}"
    abi = interpreter + ("t" if "t-" in target.abi else "")
    mac = re.fullmatch(r"macosx-(\d+)\.(\d+)-(arm64|x86_64)", target.platform)
    if (
        mac
        and mac[3] == target.machine
        and 10 <= int(mac[1]) <= 100
        and int(mac[2]) < 100
    ):
        platforms = tuple(mac_platforms((int(mac[1]), int(mac[2])), target.machine))
    elif (
        sys.platform == "linux"
        and target.platform == "linux-" + target.machine
        and target.machine == host_platform.machine()
    ):
        platforms = tuple(platform_tags())
    else:
        raise PreparationError("target_invalid")
    ordered = chain(
        cpython_tags((major, minor), abis=[abi], platforms=platforms),
        compatible_tags((major, minor), interpreter=interpreter, platforms=platforms),
    )
    result: dict[str, int] = {}
    for tag in islice(ordered, 16385):
        result.setdefault(str(tag), len(result))
        if len(result) > 16384:
            raise PreparationError("target_invalid")
    return result

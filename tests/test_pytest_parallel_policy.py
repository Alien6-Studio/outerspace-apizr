"""Reject concurrent use of the explicitly configured Docker qualification."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("flags", [["-n", "2"], ["-n", "auto"], ["--dist=each"]])
def test_real_docker_qualification_refuses_distribution_before_image_access(flags):
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *flags, "tests/oci"],
        cwd=ROOT,
        env={**os.environ, "APIZR_TEST_OCI_IMAGE": "/image-must-not-be-opened"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == pytest.ExitCode.USAGE_ERROR
    assert "APIZR_TEST_OCI_IMAGE requires serial pytest (-n 0)" in result.stderr
    assert "FileNotFoundError" not in result.stderr


def test_serial_marker_keeps_real_docker_cases_collectable():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-n",
            "0",
            "-m",
            "serial",
            "tests/oci",
            "tests/governed_repository/test_transports.py",
            "tests/governed_oci/test_tuple_results.py",
        ],
        cwd=ROOT,
        env={**os.environ, "APIZR_TEST_OCI_IMAGE": "/image-must-not-be-opened"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "tests/oci/test_integration.py::" in result.stdout
    selected = [
        line for line in result.stdout.splitlines() if line.startswith("tests/")
    ]
    dynamic = [line for line in selected if "tests/oci/" not in line]
    assert len(dynamic) == 7
    assert all("oci-container" in line for line in dynamic)
    assert "no tests collected" not in result.stdout

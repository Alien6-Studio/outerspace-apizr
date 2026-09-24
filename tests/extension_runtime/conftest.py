"""A prepared dependency-free environment for real subprocess tests."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def extension_python(tmp_path_factory):
    root = tmp_path_factory.mktemp("installed-extension") / "env"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(root)],
        check=True,
        timeout=30,
    )
    python = root / "bin/python"
    purelib = Path(
        subprocess.check_output(
            [
                str(python),
                "-I",
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ],
            text=True,
            timeout=10,
        ).strip()
    )
    source = Path(__file__).parent / "fixture_plugin.py"
    (purelib / "invocation_fixture.py").write_bytes(source.read_bytes())
    (purelib / "held_group.py").write_bytes(
        (Path(__file__).parent / "held_group.py").read_bytes()
    )
    demo = (
        Path(__file__).parents[2]
        / "examples/extension-probe/src/apizr_extension_probe/runtime.py"
    )
    (purelib / "invocation_demo.py").write_bytes(demo.read_bytes())
    (purelib / "invocation_unread.py").write_text("import time; time.sleep(30)\n")
    (purelib / "invocation_closed.py").write_text("import os; os.close(0)\n")
    return python

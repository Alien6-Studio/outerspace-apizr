"""Declare the existing trusted transitive example after building its wheels."""

import hashlib
import sys
from pathlib import Path

work = Path(sys.argv[1])
wheel = work / "locked-wheels/apizr_locked_probe-1.0.0-py3-none-any.whl"
digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
(work / "apizr.toml").write_text(
    'schema_version = "apizr.project/v1"\n'
    '\n[[plugins]]\nname = "apizr-locked-probe"\nversion = "1.0.0"\n'
    f'sha256 = "{digest}"\nrequirements = "requirements.lock"\n',
    encoding="utf-8",
)
(work / "user.toml").write_text(
    'schema_version = "apizr.user/v1"\nplugins_dir = "locked-plugins"\n',
    encoding="utf-8",
)

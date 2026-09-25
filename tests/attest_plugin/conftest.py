"""Only optional plugin tests import these packages."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for directory in ("plugins/oci/src", "plugins/attest/src"):
    sys.path.insert(0, str(ROOT / directory))

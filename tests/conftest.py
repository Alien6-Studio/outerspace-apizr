"""Make shared qualification fixtures importable with pytest's console entrypoint."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

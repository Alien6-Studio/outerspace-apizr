"""Write explicit example policies for this extracted directory."""

import json
from pathlib import Path

root = Path(__file__).resolve().parent
for name, value in {
    "operator.json": {
        "schema": "apizr.operator-policy/v1",
        "grants": [
            {
                "adapter": "repository",
                "operation": "analyze",
                "target": {"kind": "local", "root": str(root)},
                "permissions": ["source.analyze"],
            }
        ],
    },
    "readiness.json": {"execution": {"modes": ["direct"]}},
    "exposure.json": {
        "selection": {"include": ["python:api:quote"]},
        "interfaces": ["rest", "mcp"],
        "execution": {"allowed": ["direct"]},
    },
}.items():
    (root / name).write_text(json.dumps(value, indent=2) + "\n")

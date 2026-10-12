"""Call the generated quote using only the Python standard library."""

import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

request = Request(
    sys.argv[1].rstrip("/") + "/capabilities/api.quote",
    data=Path(sys.argv[2]).read_bytes(),
    headers={"Content-Type": "application/json"},
)
with urlopen(request, timeout=10) as response:
    result = json.load(response)
assert result["total_cents"] == 9180, result
print(json.dumps(result, sort_keys=True))

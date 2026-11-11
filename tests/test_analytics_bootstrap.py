"""The native module loader needs relative URL specifiers on every MkDocs page."""

import json
import re
from pathlib import Path
from urllib.parse import urljoin

import pytest
from jinja2 import Environment


@pytest.mark.parametrize(
    ("document", "relative_asset"),
    [
        ("/", "assets/javascripts/analytics-apizr.mjs"),
        ("/academy/", "../assets/javascripts/analytics-apizr.mjs"),
        ("/getting-started/install/", "../../assets/javascripts/analytics-apizr.mjs"),
    ],
)
def test_bootstrap_resolves_the_local_adapter_on_root_and_nested_pages(
    document, relative_asset
):
    root = Path(__file__).resolve().parents[1]
    template = root / "overrides/partials/integrations/analytics/google.html"
    environment = Environment(autoescape=True)
    environment.filters["url"] = lambda _path: relative_asset
    rendered = environment.from_string(template.read_text()).render(
        config={
            "extra": {
                "audience_catalogue": {},
                "analytics": {"property": "G-MX4P2Y5EG4"},
            }
        }
    )
    specifier = json.loads(re.search(r"\bfrom (\"[^\"]+\");", rendered)[1])
    assert specifier.startswith(("./", "../", "/")), "Bare module names cannot load in the browser"
    assert urljoin("https://apizr.outerspace.sh" + document, specifier) == (
        "https://apizr.outerspace.sh/assets/javascripts/analytics-apizr.mjs"
    )

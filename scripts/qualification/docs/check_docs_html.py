"""Check generated page links, anchors, canonicals and home assets without network."""

import argparse
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

BASE = "https://apizr.outerspace.sh/"


class Page(HTMLParser):
    def __init__(self, text: str):
        super().__init__()
        self.targets: set[str] = set()
        self.links: list[str] = []
        self.canonicals: list[str] = []
        self.text: list[str] = []
        self.feed(text)

    def handle_data(self, data):
        self.text.append(data)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for attr in ("id", "name"):
            if value := attrs.get(attr):
                self.targets.add(value)
        for attr in ("href", "src", "poster"):
            if value := attrs.get(attr):
                self.links.append(value)
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonicals.append(attrs.get("href") or "")


def check(site: Path) -> None:
    pages = {
        path.relative_to(site).as_posix(): Page(path.read_text())
        for path in site.rglob("*.html")
    }
    failures = []
    for name, page in pages.items():
        if name == "404.html":
            continue
        url = urljoin(BASE, name.removesuffix("index.html"))
        if page.canonicals != [url]:
            failures.append(f"{name}: canonical {page.canonicals}, expected {url}")
        for link in page.links:
            parsed = urlsplit(urljoin(url, link))
            if parsed.netloc != urlsplit(BASE).netloc or parsed.scheme != "https":
                continue
            target = unquote(parsed.path).lstrip("/")
            if not target or target.endswith("/"):
                target += "index.html"
            if not (site / target).is_file():
                failures.append(f"{name}: missing {link}")
            elif parsed.fragment and target in pages:
                anchor = unquote(parsed.fragment)
                # Material injects its consent dialog at runtime.
                if anchor != "__consent" and anchor not in pages[target].targets:
                    failures.append(f"{name}: missing anchor {link}")
    for name in (
        "reference/apizr-mcp-server",
        "reference/git-sources",
        "reference/git-ssh",
        "reference/compiler-api",
        "reference/local-extensions",
        "reference/plugin-catalog",
        "reference/plugin-authors",
        "reference/project-plugin-locks",
        "reference/extension-invocation",
        "reference/oci-service-plugin",
        "reference/attest-delivery-plugin",
        "reference/attest-oci-artifacts",
        "getting-started/user-guide/project",
    ):
        text = (site / name / "index.html").read_text()
        content = "".join(pages[f"{name}/index.html"].text)
        if "Install Apizr" not in content or "install/" not in text:
            failures.append(f"{name}: missing package availability/installation link")
        if "0.4 development — not released" in content:
            failures.append(f"{name}: obsolete development banner")
        if "(0.4)" in content:
            failures.append(f"{name}: version suffix in official guide navigation")
    for name in (
        "reference/operator-policy",
        "reference/compiler-api",
        "reference/apizr-mcp-server",
        "reference/git-sources",
        "reference/git-ssh",
        "getting-started/user-guide/project",
        "development/0.4",
    ):
        text = (site / name / "index.html").read_text()
        if "operator-policy" not in text and "operator_policy" not in text:
            failures.append(
                f"{name}: missing explicit operator authority documentation"
            )
    authority = (site / "reference/operator-policy/index.html").read_text()
    if (
        "source.analyze" not in authority
        or "authorize-repository-analysis" not in authority
    ):
        failures.append("Missing source analysis permission and stable anchor")
    for name, required in {
        "getting-started/install/index.html": (
            "publication status",
            "durable GitHub release assets",
            "catalog resolve",
            "lock check",
            "pipx",
            "attestation verify",
        ),
        "getting-started/quickstart/index.html": (
            "--operator-policy operator.json",
            "source.analyze",
            'quote: {"result": 25.0}',
            'available: {"result": true}',
        ),
        "contributing/publish-0.4/index.html": (
            "Confirmation mainteneur nécessaire",
            "Official Apizr distribution images remain deferred",
            "SHA256SUMS",
        ),
        "releases/0.4.1/index.html": (
            "0.4.1 is published and verified.",
            "d08b37d126957593a82784ef3ad096e3f8b4929d",
            "36601712772",
            "36608326995",
            "DeliveryPlan",
            "0.4.1rc1",
            "0.4.2",
        ),
        "releases/0.4.0/index.html": (
            "Apizr 0.4.0rc1",
            "Core and all three plugins published as 0.4.0rc1.",
            "source.analyze",
            "structuredContent",
            "0.4.1",
            "0.4.2",
        ),
    }.items():
        text = "".join(pages[name].text)
        for token in required:
            if token not in text:
                failures.append(f"{name}: missing release guidance: {token}")
    permissions = "".join(pages["reference/operator-policy/index.html"].text)
    for token in (
        "operator_policy_required",
        "CLI/Python parity: plan, REST bundle and MCP bundle",
        "source.analyze",
    ):
        if token not in permissions:
            failures.append(f"Current source permission example is missing: {token}")
    home = (site / "index.html").read_text()
    for required in (
        "getting-started/quickstart/",
        "getting-started/install/",
        "releases/0.4.1/",
        "package availability",
        "Choose your next step",
        "assets/images/illustration.png",
        "assets/videos/paris-route.jpg",
        "assets/javascripts/video.js",
        "u8e0fi2m80M",
        "build-info.json",
    ):
        if required not in home:
            failures.append(f"Home is missing {required}")
    for name in (
        "getting-started/install/index.html",
        "getting-started/quickstart/index.html",
        "getting-started/introduction/index.html",
        "architecture/overview/index.html",
    ):
        text = (site / name).read_text()
        visible = "".join(pages[name].text)
        for obsolete in (
            "Try the 0.4 candidate",
            "Evaluate 0.4 — unreleased",
            "Install the published release",
            "Latest published stable",
        ):
            if obsolete in visible:
                failures.append(f"{name}: obsolete version choice: {obsolete}")
        if 'data-md-component="source"' in text:
            failures.append(
                f"{name}: repository widget can inject a stale release badge"
            )
        headings = re.findall(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", text, re.S)
        if any(re.search(r"\bv[12]\b", "".join(Page(h).text)) for h in headings):
            failures.append(f"{name}: schema version in a reader-facing title")
    for name in (
        "getting-started/quickstart-0.3/index.html",
        "getting-started/introduction-0.3/index.html",
    ):
        if name in pages:
            failures.append(f"{name}: historical walkthrough must not be published")
    quickstart = (site / "getting-started/quickstart/index.html").read_text()
    for required in (
        "--operator-policy operator.json",
        "/37259eaf0a231d747f1ae0eb2f7ce94b2a2b306f/examples/repository-shop/",
        "python:api:quote",
        "python:inventory:available",
        'quote: {"result": 25.0}',
        'available: {"result": true}',
        "mcpServers",
        "The full journey",
    ):
        if required not in quickstart and required not in "".join(
            Page(quickstart).text
        ):
            failures.append(f"Quickstart is missing {required}")
    quickstart_page = pages["getting-started/quickstart/index.html"]
    for anchor in (
        "choose-your-interface",
        "use-mcp",
        "generate-the-mcp-bundle",
        "connect-a-client-and-make-two-calls",
        "connect-an-ai-client",
        "test-with-python",
        "use-rest-instead",
        "continue-with-your-own-code",
    ):
        if anchor not in quickstart_page.targets:
            failures.append(
                f"Quickstart lost a reading choice or published anchor: {anchor}"
            )
    for name, anchor in (
        ("index.html", "apizr"),
        ("getting-started/user-guide/rest/index.html", "generate-a-rest-interface"),
        ("getting-started/user-guide/mcp/index.html", "generate-an-mcp-server"),
        (
            "getting-started/user-guide/exposure/index.html",
            "plan-explicit-repository-exposure",
        ),
    ):
        if anchor not in pages[name].targets:
            failures.append(f"{name}: lost published anchor {anchor}")
    journey = pages["getting-started/introduction/index.html"]
    for anchor in (
        "start-here",
        "introduction",
        "install",
        "walk-through-a-small-repository",
        "understand-the-decisions",
        "choose-your-next-step",
    ):
        if anchor not in journey.targets:
            failures.append(f"Full journey lost published anchor: {anchor}")
    if failures:
        raise ValueError("\n".join(failures))
    print(
        f"Checked {len(pages)} HTML pages, links, anchors, canonicals and home assets"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path, nargs="?", default=Path("site"))
    check(parser.parse_args().site)

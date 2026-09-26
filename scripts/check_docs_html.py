"""Check generated page links, anchors, canonicals and home assets without network."""

import argparse
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
        "reference/extension-invocation",
        "reference/oci-service-plugin",
        "reference/attest-delivery-plugin",
        "reference/attest-oci-artifacts",
        "getting-started/user-guide/project",
    ):
        text = (site / name / "index.html").read_text()
        if (
            "0.4 development — not released" not in text
            or "development/0.4/#install-a-development-wheel" not in text
        ):
            failures.append(f"{name}: missing development status/installation link")
    home = (site / "index.html").read_text()
    for required in (
        "getting-started/quickstart/",
        "development/0.4/",
        "Preparing 0.4",
        "Latest published stable: 0.3.0",
        "assets/images/illustration.png",
        "assets/videos/paris-route.jpg",
        "assets/javascripts/video.js",
        "u8e0fi2m80M",
        "build-info.json",
    ):
        if required not in home:
            failures.append(f"Home is missing {required}")
    quickstart = (site / "getting-started/quickstart/index.html").read_text()
    for required in (
        "outerspace-apizr==0.3.0",
        "/v0.3.0/examples/repository-shop/",
        "python:api:quote",
        "python:inventory:available",
        "quote: 25.0",
        "available: true",
        "mcpServers",
        "The full journey",
    ):
        if required not in quickstart and required not in "".join(
            Page(quickstart).text
        ):
            failures.append(f"Quickstart is missing {required}")
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

"""Build an exact public catalogue after MkDocs has populated every page."""

import hashlib
import re
from html.parser import HTMLParser


class PersonalControls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag in {"form", "textarea", "select"} or "data-analytics-private" in attrs:
            self.found = True
        if "contenteditable" in attrs and attrs["contenteditable"] != "false":
            self.found = True
        if tag == "input" and "disabled" not in attrs:
            self.found = True


def public_path(value):
    path = "/" + value.lstrip("/")
    if not re.fullmatch(r"/[A-Za-z0-9_./-]*", path) or ".." in path.split("/"):
        return None
    trailing = path.endswith("/")
    path = "/" + "/".join(part for part in path.split("/") if part not in {"", "."})
    if trailing and path != "/":
        path += "/"
    parts = path.strip("/").split("/")
    section = (
        parts[1]
        if parts[0] in {"fr", "en", "de", "es", "it"} and len(parts) > 1
        else parts[0]
    )
    if section in {
        "account",
        "auth",
        "contact",
        "dashboard",
        "login",
        "logout",
        "register",
        "signup",
        "signin",
        "sign-in",
        "callback",
        "oauth",
        "profile",
        "checkout",
        "reset-password",
        "forgot-password",
        "preview",
        "private",
        "admin",
        "api",
    }:
        return None
    return path


def content_id(source):
    stem = source.rsplit(".", 1)[0]
    value = "doc_" + re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    if len(value) > 100:
        value = value[:83] + "_" + hashlib.sha256(source.encode()).hexdigest()[:16]
    return value


def on_env(env, config, files):
    catalogue = {}
    identifiers = set()
    for file in files.documentation_pages():
        page = file.page
        if (
            page is None
            or page.meta.get("draft")
            or page.meta.get("private")
            or page.meta.get("status") == "draft"
            or page.meta.get("analytics") is False
        ):
            continue
        controls = PersonalControls()
        controls.feed(page.content)
        path = public_path(file.url)
        if controls.found or path is None:
            continue
        identifier = content_id(file.src_uri)
        if path in catalogue or identifier in identifiers:
            raise ValueError("Ambiguous public analytics catalogue identity")
        identifiers.add(identifier)
        catalogue[path] = {
            "content_id": identifier,
            "content_type": "home"
            if path == "/"
            else "academy"
            if path.startswith("/academy/")
            else "documentation",
        }
    config.extra["audience_catalogue"] = catalogue
    return env


def on_page_context(context, page, config, nav):
    context["audience_path"] = public_path(page.file.url)
    context["audience_page"] = config.extra["audience_catalogue"].get(
        context["audience_path"]
    )
    return context

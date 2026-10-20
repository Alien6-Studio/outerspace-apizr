"""Read-only ecosystem checks, independent of Apizr and release qualification.

Only documented public APIs are enabled for scheduled checks. HTML inspections
are explicit, best-effort checks; a successful HTTP response alone proves nothing
about a listing. Evidence snapshots contain observations, not executable content.
"""

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
from collections import Counter
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
USER_AGENT = (
    "ApizrEcosystemAudit/1.0 (+https://github.com/Alien6-Studio/outerspace-apizr)"
)
LIMIT = 2_000_000
DEFAULT_TOOLS = {
    "apizr_analyze",
    "apizr_readiness",
    "apizr_plan_exposure",
    "apizr_experiment_list",
    "apizr_experiment_show",
    "apizr_experiment_diff",
}


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return result.astimezone(UTC)


def secure_url(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
    ):
        raise ValueError("Only public HTTPS URLs without credentials are supported")
    return f"https://{parsed.netloc}"


class Page(HTMLParser):
    def __init__(self, body: str):
        super().__init__()
        self.parts: list[str] = []
        self.links: list[str] = []
        self.hidden = 0
        self.feed(body)
        self.text = re.sub(r"\s+", " ", " ".join(self.parts))

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def extract(probe: dict, body: str) -> dict:
    """Conservative, identity-bound parsers. Never search arbitrary version text."""
    kind = probe["parser"]
    observed: dict = {"identity_verified": False, "version": None, "issues": []}
    if kind in {
        "pypi",
        "registry",
        "piwheels",
        "deps",
        "github_release",
        "tracevero",
        "smithery",
    }:
        data = json.loads(body)
        if kind == "pypi":
            info = data["info"]
            observed.update(
                identity_verified=info["name"] == probe["identity"],
                version=info["version"],
                description=info.get("summary"),
                requires_python=info.get("requires_python"),
            )
        elif kind == "registry":
            server = data["server"]
            observed.update(
                identity_verified=server["name"] == probe["identity"],
                version=server["version"],
                description=server.get("description"),
                package_versions=[p["version"] for p in server.get("packages", [])],
            )
            if any(v != server["version"] for v in observed["package_versions"]):
                observed["issues"].append("Registry server and package versions differ")
        elif kind == "piwheels":
            versions = [
                version
                for version, release in data["releases"].items()
                if re.fullmatch(r"\d+\.\d+\.\d+", version)
                and not release.get("prerelease")
                and not release.get("yanked")
            ]
            observed.update(
                identity_verified=data["package"] == probe["identity"],
                version=max(versions, key=lambda v: tuple(map(int, v.split("."))))
                if versions
                else None,
                description=data.get("summary"),
            )
        elif kind == "deps":
            defaults = [v for v in data["versions"] if v.get("isDefault")]
            observed.update(
                identity_verified=data["packageKey"]
                == {"system": "PYPI", "name": probe["identity"]},
                version=defaults[0]["versionKey"]["version"]
                if len(defaults) == 1
                else None,
            )
        elif kind == "tracevero":
            fields = {item["schluessel"]: item["wert"] for item in data["merkmale"]}
            observed.update(
                identity_verified=data["schluessel"] == probe["identity"],
                version=fields.get("version"),
                description=data["anbietertext"]["text"],
                platform_checked_at=data.get("zuletzt_geprueft"),
            )
        elif kind == "smithery":
            matches = [
                s
                for s in data["servers"]
                if s.get("homepage", "").rstrip("/") == probe["identity"]
            ]
            observed.update(
                identity_verified=len(matches) == 1,
                matched_names=[s["qualifiedName"] for s in matches],
                pagination=data.get("pagination"),
            )
            # Semantic search with non-matching results is incomplete evidence.
        else:
            observed.update(
                identity_verified=data["html_url"] == probe["identity"],
                version=data["tag_name"].removeprefix("v"),
                published_at=data.get("published_at"),
            )
    elif kind == "homebrew":
        observed["identity_verified"] = (
            "class Apizr < Formula" in body and probe["identity"] in body
        )
        match = re.search(r"/releases/download/v([^/]+)/outerspace_apizr-", body)
        observed["version"] = match[1] if match else None
    else:
        page = Page(body)
        # A query echo or a navigation link is not evidence of a listing.
        required = probe.get("identity_text")
        observed["identity_verified"] = bool(required and required in page.text)
        if link := probe.get("identity_link"):
            observed["identity_verified"] &= link in page.links
        if kind == "search":
            observed["identity_verified"] = False
            observed["absence_verified"] = all(
                token in page.text for token in probe["absence_markers"]
            )
        if pattern := probe.get("version_pattern"):
            # Patterns target labelled version fields, never the entire README.
            source = body if probe.get("version_in_markup") else page.text
            match = re.search(pattern, source)
            observed["version"] = match[1] if match else None
        if kind == "glama":
            prefix = "/mcp/servers/Alien6-Studio/outerspace-apizr/tools/"
            tools = sorted(
                {
                    link.removeprefix(prefix)
                    for link in page.links
                    if link.startswith(prefix)
                }
            )
            observed["tool_names"] = tools
            if tools and not DEFAULT_TOOLS.issubset(tools):
                observed["issues"].append("Inspection omits default experiment tools")
        for marker, issue in probe.get("obsolete_markers", {}).items():
            if marker in page.text:
                observed["issues"].append(issue)
    if not observed["identity_verified"]:
        observed["version"] = None
        observed["issues"] = []
    return observed


def observation(probe: dict, response: dict) -> dict:
    result = {k: v for k, v in response.items() if k != "body"}
    result["url"] = probe["url"]
    result["observed"] = {"identity_verified": False, "version": None, "issues": []}
    if response.get("status") == 200 and not response.get("error"):
        body = response.get("body", "")
        result["sha256"] = hashlib.sha256(body.encode()).hexdigest()
        try:
            result["observed"] = extract(probe, body)
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
            result["error"] = f"Unrecognised response: {type(exc).__name__}"
    elif response.get("status") == 404 and probe.get("authoritative_404"):
        result["observed"]["absence_verified"] = True
        result.pop("error", None)
    return result


class Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts: set[str]):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if secure_url(newurl) not in self.hosts:
            raise ValueError("Redirect outside reviewed HTTPS origins")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Client:
    """No retries, credentials, installation, execution, or challenge bypass."""

    def __init__(self, timeout: float = 10, interval: float = 2):
        self.timeout = timeout
        self.interval = interval
        self.last: dict[str, float] = {}
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.intervals: dict[str, float] = {}

    def request(self, url: str, hosts: set[str]) -> dict:
        origin = secure_url(url)
        delay = self.intervals.get(origin, self.interval) - (
            time.monotonic() - self.last.get(origin, 0)
        )
        if delay > 60:
            return {
                "status": None,
                "error": "Access policy requires a later check; request deferred",
            }
        if delay > 0:
            time.sleep(delay)
        self.last[origin] = time.monotonic()
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json,text/html;q=0.9,*/*;q=0.5",
                },
            )
            opener = urllib.request.build_opener(Redirects(hosts))
            with opener.open(request, timeout=self.timeout) as response:
                content = response.read(LIMIT + 1)
                if len(content) > LIMIT:
                    raise ValueError("Response exceeds 2 MB limit")
                return {
                    "status": response.status,
                    "final_url": response.url,
                    "body": content.decode("utf-8"),
                }
        except urllib.error.HTTPError as exc:
            return {
                "status": exc.code,
                "error": f"HTTP {exc.code}",
                "retry_after": exc.headers.get("Retry-After"),
            }
        except (OSError, ValueError, urllib.error.URLError) as exc:
            return {"status": None, "error": f"{type(exc).__name__}: {exc}"}

    def allowed(self, url: str) -> bool:
        origin = secure_url(url)
        if origin not in self.robots:
            response = self.request(origin + "/robots.txt", {origin})
            robot = urllib.robotparser.RobotFileParser()
            if response.get("status") == 200:
                robot.parse(response["body"].splitlines())
                self.robots[origin] = robot
                rate = robot.request_rate(USER_AGENT)
                self.intervals[origin] = max(
                    self.interval,
                    float(robot.crawl_delay(USER_AGENT) or 0),
                    float(rate.seconds) / float(rate.requests) if rate else 0,
                )
            elif response.get("status") == 404:
                robot.parse([])
                self.robots[origin] = robot
            else:
                self.robots[origin] = None
        policy = self.robots[origin]
        return policy is not None and policy.can_fetch(USER_AGENT, url)

    def fetch(self, probe: dict) -> dict:
        url = probe["url"]
        hosts = {secure_url(url), *probe.get("redirect_origins", [])}
        # Check access policies on every permitted redirect origin as well.
        if not all(self.allowed(origin + "/") for origin in hosts) or not self.allowed(
            url
        ):
            return {
                "checked_at": datetime.now(UTC).isoformat(),
                "error": "Access policy disallows checking or could not be verified",
                "status": None,
            }
        response = self.request(url, hosts)
        return response | {"checked_at": datetime.now(UTC).isoformat()}


def freshness(value: str | None, now: datetime, days: int) -> str:
    if not value:
        return "unknown"
    age = now - instant(value)
    if age < timedelta(0):
        return "future"
    return "stale" if age > timedelta(days=days) else "fresh"


def report(inventory: dict, evidence: dict, now: datetime) -> dict:
    rows = []
    for entry in inventory["listings"]:
        current = evidence.get(entry["id"], {})
        # A snapshot for another URL must not validate this inventory entry.
        if current and current.get("url") != entry["probe"]["url"]:
            raise ValueError(f"Evidence URL mismatch: {entry['id']}")
        observed = current.get("observed", {})
        age = freshness(current.get("checked_at"), now, inventory["freshness_days"])
        verified = age == "fresh" and not current.get("error")
        version = observed.get("version") if verified else None
        comparison = (
            "unknown"
            if version is None
            else "match"
            if version == inventory["reference_version"]
            else "mismatch"
        )
        status = "indeterminate"
        if verified and observed.get("absence_verified"):
            status = "absent_confirmed"
        elif verified and observed.get("identity_verified"):
            status = (
                "obsolete"
                if comparison == "mismatch" or observed.get("issues")
                else "confirmed"
            )
        rows.append(
            {
                "id": entry["id"],
                "platform": entry["platform"],
                "url": entry["url"],
                "status": status,
                "checked_at": current.get("checked_at"),
                "freshness": age,
                "version": version,
                "version_comparison": comparison,
                "observation": current,
                "last_review": entry["review"],
                "review_freshness": freshness(
                    entry["review"]["checked_at"], now, inventory["freshness_days"]
                ),
                "assessment_freshness": freshness(
                    entry["review"].get("score", {}).get("assessed_at"),
                    now,
                    inventory["freshness_days"],
                ),
                "update": entry["update"],
            }
        )
    return {
        "schema_version": 1,
        "reference_version": inventory["reference_version"],
        "as_of": now.isoformat(),
        "counts": dict(Counter(row["status"] for row in rows)),
        "listings": rows,
    }


def markdown(result: dict) -> str:
    def cell(value):
        return (
            str(value if value is not None else "unknown")
            .replace("|", "\\|")
            .replace("\n", " ")
        )

    lines = [
        "# Ecosystem verification",
        "",
        f"Reference: **{result['reference_version']}** · As of: {result['as_of']}",
        "",
        "Current observations and dated editorial reviews are independent. A 200 response alone is not a confirmed listing. Unknown versions are never matches. Historical scores are platform assessments, not product qualification.",
        "",
        "| Platform | Current status | Version | Comparison | Evidence age | Last editorial review |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in result["listings"]:
        review = row["last_review"]
        lines.append(
            "| "
            + " | ".join(
                map(
                    cell,
                    [
                        f"[{row['platform']}]({row['url']})",
                        row["status"],
                        row["version"],
                        row["version_comparison"],
                        row["freshness"],
                        f"{review['status']} ({review['checked_at']}; {row['review_freshness']})",
                    ],
                )
            )
            + " |"
        )
    for row in result["listings"]:
        lines += [
            "",
            f"## {row['platform']}",
            "",
            f"Listing or scoped search: {row['url']}",
            "",
            f"Probe: {row['observation'].get('url', 'not run')} · Checked: {row['checked_at'] or 'not run'}",
            "",
            row["last_review"]["findings"],
            "",
            f"Update: {row['update']['instructions']}",
            "",
        ]
        if error := row["observation"].get("error"):
            lines += [f"Current check: {error}", ""]
        if score := row["last_review"].get("score"):
            lines += [
                f"Historical assessment: {score['value']} · Assessed: {score.get('assessed_at') or 'unknown'} ({row['assessment_freshness']}) · Captured: {row['last_review']['checked_at']}",
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=ROOT / "registry-audit.json")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true")
    mode.add_argument(
        "--fixtures", type=Path, help="Local raw HTTP response fixtures; no networking"
    )
    mode.add_argument(
        "--replay", type=Path, help="Replay dated observations; no networking"
    )
    parser.add_argument(
        "--include-manual",
        action="store_true",
        help="Also inspect reviewed HTML probes once, respecting access policy",
    )
    parser.add_argument(
        "--as-of", help="Timezone-aware report timestamp (defaults to current UTC)"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 for drift/absence; 2 for incomplete or stale evidence",
    )
    args = parser.parse_args(argv)
    inventory = json.loads(args.inventory.read_text())
    if inventory["schema_version"] != 1:
        raise ValueError("Unsupported inventory schema")
    ids = [entry["id"] for entry in inventory["listings"]]
    if len(ids) != len(set(ids)) or any(
        not re.fullmatch(r"[a-z0-9-]+", name) for name in ids
    ):
        raise ValueError("Listing IDs must be unique path-safe names")
    evidence = {}
    if args.replay:
        evidence = json.loads(args.replay.read_text())
    else:
        client = Client()
        for entry in inventory["listings"]:
            probe = entry["probe"]
            if args.fixtures:
                path = args.fixtures / (entry["id"] + ".json")
                response = (
                    json.loads(path.read_text())
                    if path.exists()
                    else {"error": "Fixture missing"}
                )
            elif probe["automatic"] or args.include_manual:
                response = client.fetch(probe)
            else:
                response = {"error": "Manual review only; scheduled probe disabled"}
            evidence[entry["id"]] = observation(probe, response)
    # Live captures happen after startup; evaluate their age after collection.
    now = instant(args.as_of) if args.as_of else datetime.now(UTC)
    result = report(inventory, evidence, now)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, data in [("observations.json", evidence), ("report.json", result)]:
        (args.output / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        )
    (args.output / "report.md").write_text(markdown(result))
    print(json.dumps(result["counts"], sort_keys=True))
    if args.strict:
        if any(row["status"] == "indeterminate" for row in result["listings"]):
            return 2
        if any(
            row["status"] in {"obsolete", "absent_confirmed"}
            for row in result["listings"]
        ):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

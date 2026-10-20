"""Offline checks of uncertain, stale, malformed and rate-limited evidence."""

import copy
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

from ecosystem import verify

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
NOW = verify.instant("2026-10-20T12:09:00Z")
REPOSITORY = "https://github.com/Alien6-Studio/outerspace-apizr"


class RegistryAuditTests(unittest.TestCase):
    def setUp(self):
        self.network_guard = patch(
            "urllib.request.OpenerDirector.open",
            side_effect=AssertionError("Network access is forbidden in offline tests"),
        )
        self.network_guard.start()
        self.addCleanup(self.network_guard.stop)
        self.inventory = json.loads(
            (ROOT / "ecosystem/registry-audit.json").read_text()
        )
        self.entries = {entry["id"]: entry for entry in self.inventory["listings"]}

    def fixture(self, name):
        return json.loads((FIXTURES / (name + ".json")).read_text())

    def check(self, entry_id, fixture):
        return verify.observation(self.entries[entry_id]["probe"], fixture)

    def row(self, entry_id, observation, now=NOW):
        inventory = self.inventory | {"listings": [self.entries[entry_id]]}
        return verify.report(inventory, {entry_id: observation}, now)["listings"][0]

    def test_pypi_current_version_and_identity(self):
        current = self.check("pypi", self.fixture("pypi"))
        self.assertEqual(self.row("pypi", current)["status"], "confirmed")
        self.assertEqual(current["observed"]["version"], "0.4.6")
        payload = self.fixture("pypi")
        payload["body"] = payload["body"].replace("outerspace-apizr", "another-project")
        wrong = self.check("pypi", payload)
        self.assertEqual(self.row("pypi", wrong)["status"], "indeterminate")
        self.assertIsNone(wrong["observed"]["version"])

    def test_version_mismatch_is_not_assumed_to_be_an_older_version(self):
        payload = self.fixture("pypi")
        payload["body"] = payload["body"].replace("0.4.6", "0.5.0")
        row = self.row("pypi", self.check("pypi", payload))
        self.assertEqual(row["version_comparison"], "mismatch")
        self.assertEqual(row["status"], "obsolete")

    def test_registry_compares_package_and_server_versions(self):
        current = self.check("official-mcp", self.fixture("registry"))
        self.assertTrue(current["observed"]["issues"])
        self.assertEqual(self.row("official-mcp", current)["status"], "obsolete")

    def test_piwheels_uses_numeric_stable_non_yanked_releases(self):
        observed = self.check("piwheels", self.fixture("piwheels"))["observed"]
        self.assertEqual(observed["version"], "0.4.10")

    def test_tracevero_reads_the_documented_entry_api(self):
        current = self.check("tracevero", self.fixture("tracevero"))
        self.assertEqual(self.row("tracevero", current)["version_comparison"], "match")

    def test_deps_uses_default_not_order_or_readme(self):
        current = self.check("deps-dev", self.fixture("deps"))
        self.assertEqual(current["observed"]["version"], "0.4.6")

    def test_glama_readme_version_does_not_validate_inspection(self):
        current = self.check("glama", self.fixture("glama"))
        row = self.row("glama", current)
        self.assertEqual(row["status"], "obsolete")
        self.assertIsNone(row["version"])
        self.assertEqual(row["assessment_freshness"], "stale")
        self.assertEqual(row["freshness"], "fresh")

    def test_marketplace_uses_version_field_not_readme_example(self):
        current = self.check("vscode-marketplace", self.fixture("marketplace"))
        self.assertEqual(current["observed"]["version"], "0.4.6")

    def test_unknown_html_and_client_rendered_search_are_indeterminate(self):
        for entry_id in ["glama", "lobehub", "mcp-so", "pulsemcp"]:
            with self.subTest(entry_id=entry_id):
                row = self.row(entry_id, self.check(entry_id, self.fixture("unknown")))
                self.assertEqual(row["status"], "indeterminate")
                self.assertEqual(row["version_comparison"], "unknown")

    def test_smithery_semantic_nonmatches_do_not_prove_absence(self):
        row = self.row("smithery", self.check("smithery", self.fixture("smithery")))
        self.assertEqual(row["status"], "indeterminate")

    def test_explicit_platform_search_absence_is_scoped(self):
        row = self.row("mcp-so", self.check("mcp-so", self.fixture("search")))
        self.assertEqual(row["status"], "absent_confirmed")
        self.assertEqual(row["version_comparison"], "unknown")

    def test_404_confirms_only_an_explicit_authoritative_lookup(self):
        response = {"status": 404, "error": "HTTP 404", "checked_at": NOW.isoformat()}
        absent = self.row("homebrew-core", self.check("homebrew-core", response))
        unknown = self.row("glama", self.check("glama", response))
        self.assertEqual(absent["status"], "absent_confirmed")
        self.assertEqual(unknown["status"], "indeterminate")

    def test_403_429_timeout_and_malformed_json_preserve_last_review(self):
        for response in [
            {"status": 403, "error": "HTTP 403"},
            {"status": 429, "error": "HTTP 429", "retry_after": "600"},
            {"status": None, "error": "Timeout"},
            {"status": 200, "body": "<html>challenge</html>"},
            {"status": 200, "body": '{"info": []}'},
        ]:
            with self.subTest(response=response):
                response["checked_at"] = NOW.isoformat()
                row = self.row("pypi", self.check("pypi", response))
                self.assertEqual(row["status"], "indeterminate")
                self.assertIsNone(row["version"])
                self.assertEqual(row["last_review"]["version"], "0.4.6")

    def test_missing_stale_and_future_observations_never_pass(self):
        current = self.check("pypi", self.fixture("pypi"))
        for date, expected in [
            (None, "unknown"),
            ("2026-09-20T00:00:00Z", "stale"),
            ("2026-10-21T00:00:00Z", "future"),
        ]:
            with self.subTest(date=date):
                row = self.row("pypi", current | {"checked_at": date})
                self.assertEqual(row["freshness"], expected)
                self.assertEqual(row["status"], "indeterminate")
                self.assertEqual(row["version_comparison"], "unknown")

    def test_evidence_from_a_different_url_is_rejected(self):
        current = self.check("pypi", self.fixture("pypi"))
        with self.assertRaisesRegex(ValueError, "URL mismatch"):
            self.row("pypi", current | {"url": "https://example.org"})

    def test_replay_writes_json_markdown_without_network_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            args = [
                "--replay",
                str(ROOT / "ecosystem/evidence/2026-10-20.json"),
                "--as-of",
                NOW.isoformat(),
                "--output",
                directory,
            ]
            self.assertEqual(verify.main(args), 0)
            first = {p.name: p.read_bytes() for p in Path(directory).iterdir()}
            self.assertEqual(verify.main(args), 0)
            self.assertEqual(
                first, {p.name: p.read_bytes() for p in Path(directory).iterdir()}
            )
            report = json.loads(first["report.json"])
            self.assertEqual(len(report["listings"]), 29)
            self.assertIn(b"unknown", first["report.md"])
            self.assertEqual(verify.main(args + ["--strict"]), 2)

    def test_raw_fixture_cli_and_strict_drift_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory = copy.deepcopy(self.inventory)
            inventory["listings"] = [self.entries["piwheels"]]
            path = Path(directory) / "inventory.json"
            path.write_text(json.dumps(inventory))
            self.assertEqual(
                verify.main(
                    [
                        "--inventory",
                        str(path),
                        "--fixtures",
                        str(FIXTURES),
                        "--as-of",
                        NOW.isoformat(),
                        "--output",
                        str(Path(directory) / "output"),
                        "--strict",
                    ]
                ),
                1,
            )

    def test_live_age_is_measured_after_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            path.write_text(
                json.dumps(self.inventory | {"listings": [self.entries["pypi"]]})
            )

            def capture(_probe):
                return self.fixture("pypi") | {
                    "checked_at": datetime.now(UTC).isoformat()
                }

            with patch.object(verify.Client, "fetch", side_effect=capture):
                self.assertEqual(
                    verify.main(
                        ["--inventory", str(path), "--live", "--output", directory]
                    ),
                    0,
                )
            result = json.loads((Path(directory) / "report.json").read_text())
            self.assertEqual(result["listings"][0]["status"], "confirmed")

    def test_secure_urls_and_redirect_allowlist(self):
        for url in [
            "http://example.org",
            "file:///etc/passwd",
            "https://user:secret@example.org/",
            "https://example.org:8443/",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                verify.secure_url(url)
        redirects = verify.Redirects({"https://example.org"})
        with self.assertRaisesRegex(ValueError, "Redirect outside"):
            redirects.redirect_request(
                urllib.request.Request("https://example.org"),
                None,
                302,
                "Found",
                {},
                "https://other.org/login",
            )

    def test_robots_denial_and_failed_policy_lookup_skip_target(self):
        for response in [
            {"status": 200, "body": "User-agent: *\nDisallow: /\n"},
            {"status": 503, "error": "HTTP 503"},
        ]:
            client = verify.Client()
            with patch.object(client, "request", return_value=response) as request:
                result = client.fetch(self.entries["pypi"]["probe"])
                self.assertIn("Access policy", result["error"])
                self.assertEqual(request.call_count, 1)

    def test_robots_crawl_delay_is_retained_and_policy_cached(self):
        client = verify.Client()
        with patch.object(
            client,
            "request",
            return_value={
                "status": 200,
                "body": "User-agent: *\nCrawl-delay: 7\nAllow: /\n",
            },
        ) as request:
            self.assertTrue(client.allowed("https://example.org/pypi/pkg/json"))
            self.assertTrue(client.allowed("https://example.org/other"))
            self.assertEqual(client.intervals["https://example.org"], 7)
            self.assertEqual(request.call_count, 1)

    def test_timeouts_size_bound_and_no_retry_for_429(self):
        client = verify.Client(timeout=3, interval=0)
        opener = Mock()
        error = urllib.error.HTTPError(
            "https://example.org", 429, "rate limited", {"Retry-After": "60"}, None
        )
        opener.open.side_effect = error
        with patch("urllib.request.build_opener", return_value=opener):
            response = client.request("https://example.org", {"https://example.org"})
        self.assertEqual(response["retry_after"], "60")
        opener.open.assert_called_once()
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 3)
        opener = Mock()
        large = io.BytesIO(b"x" * (verify.LIMIT + 1))
        opener.open.return_value = large
        with patch("urllib.request.build_opener", return_value=opener):
            result = client.request("https://example.org", {"https://example.org"})
        self.assertIn("exceeds", result["error"])

    def test_canonical_copy_respects_public_field_limits(self):
        descriptions = json.loads(
            (ROOT / "ecosystem/canonical-descriptions.json").read_text()
        )
        for variant in ["product", "analysis_server"]:
            self.assertLessEqual(len(descriptions[variant]["short"]), 160)
            self.assertLessEqual(len(descriptions[variant]["standard"]), 500)
        self.assertLessEqual(len(descriptions["analysis_server"]["registry"]), 100)


if __name__ == "__main__":
    unittest.main()

"""Failure reasons stay legible without serving exception text.

An UNAVAILABLE envelope carries the reason (CANON Law 1): a missing tool,
missing authentication, an exit or HTTP status, a timeout. Raw exception
messages, stderr, URLs and upstream bodies are never served (CodeQL
py/stack-trace-exposure). Every provider is mocked; nothing is sent to
GitHub, Cloudflare, Hugging Face or a DNS resolver.
"""
import contextlib
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import requests

from backend import main
from backend.cache import ResponseCache
from backend.collectors import base, cloudflare, dns, github, huggingface, receipts

# Stands in for what upstream text can carry: a resolver address, a proxy host
# and a credential-shaped token.
LEAK = "LEAK 10.255.0.53 https://proxy.internal.example/v3?token=ghp_SENTINEL"
SNAPSHOT_DIR = os.path.join(os.path.dirname(main.__file__), "snapshot")


def gh_result(returncode, stderr=""):
    return subprocess.CompletedProcess(["gh"], returncode, "", stderr)


def http_response(status, body=b"{}"):
    resp = requests.Response()
    resp.status_code = status
    resp.url = "https://api.example/" + LEAK
    resp._content = body
    return resp


def served_reasons(node, path=""):
    """Every `reason` string in a JSON document, with its path."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "reason" and isinstance(value, str):
                yield f"{path}/{key}", value
            else:
                yield from served_reasons(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from served_reasons(value, f"{path}/{index}")


class FailureReasonTests(unittest.TestCase):
    def test_collector_reason_is_served(self):
        self.assertEqual(
            base.failure_reason(base.CollectorUnavailable("dig exited with status 9")),
            "dig exited with status 9",
        )

    def test_timeout_reports_its_limit_not_the_command(self):
        exc = subprocess.TimeoutExpired(["gh", "api", LEAK], 25)
        self.assertEqual(base.failure_reason(exc), "timed out after 25s")

    def test_other_exceptions_are_named_by_kind_only(self):
        for exc in (RuntimeError(LEAK), ValueError(LEAK), OSError(LEAK), KeyError(LEAK),
                    requests.ConnectionError(LEAK), json.JSONDecodeError(LEAK, "x", 0)):
            with self.subTest(exc=type(exc).__name__):
                self.assertEqual(base.failure_reason(exc), type(exc).__name__)


class GithubReasonTests(unittest.TestCase):
    def envelopes(self):
        return (
            github.repo_meta("a11oy"),
            github.repo_head("a11oy"),
            github.ci_runs("a11oy"),
            github.open_issues_by_repo(),
            github.workflow_observation("a11oy"),
        )

    def test_missing_gh_is_named_in_every_envelope(self):
        with patch.object(github.shutil, "which", return_value=None), patch.object(
            github.subprocess, "run"
        ) as run:
            envelopes = self.envelopes()
        run.assert_not_called()
        for env in envelopes:
            self.assertEqual(env["truth_state"], "UNAVAILABLE")
            self.assertEqual(env["reason"], "gh CLI not found on PATH")

    def test_unauthenticated_gh_is_named_without_its_stderr(self):
        stderr = "To get started with GitHub CLI, please run:  gh auth login\n" + LEAK
        with patch.object(github.shutil, "which", return_value="/usr/bin/gh"), patch.object(
            github.subprocess, "run", return_value=gh_result(4, stderr)
        ):
            envelopes = self.envelopes()
        for env in envelopes:
            self.assertEqual(env["truth_state"], "UNAVAILABLE")
            self.assertEqual(
                env["reason"],
                "gh is not authenticated (exit 4); set GH_TOKEN or run gh auth login",
            )

    def test_failed_gh_keeps_exit_and_http_status_but_not_stderr(self):
        cases = (
            ("gh: Not Found (HTTP 404)\n" + LEAK, "gh exited with status 1 (HTTP 404)"),
            ("HTTP 401: Bad credentials (" + LEAK + ")", "gh exited with status 1 (HTTP 401)"),
            ("failed to get runs: HTTP 403 (" + LEAK + ")", "gh exited with status 1 (HTTP 403)"),
            (LEAK, "gh exited with status 1"),
            ("", "gh exited with status 1"),
        )
        for stderr, expected in cases:
            with self.subTest(stderr=stderr[:40]):
                with patch.object(github.shutil, "which", return_value="/usr/bin/gh"), patch.object(
                    github.subprocess, "run", return_value=gh_result(1, stderr)
                ):
                    env = github.ci_runs("a11oy")
                self.assertEqual(env["truth_state"], "UNAVAILABLE")
                self.assertEqual(env["reason"], expected)

    def test_gh_timeout_reports_the_limit_it_was_given(self):
        def timeout(args, **kwargs):
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])

        with patch.object(github.shutil, "which", return_value="/usr/bin/gh"), patch.object(
            github.subprocess, "run", side_effect=timeout
        ):
            self.assertEqual(github.ci_runs("a11oy")["reason"], f"timed out after {github.GH_TIMEOUT}s")
            self.assertEqual(github.workflow_observation("a11oy")["reason"], "timed out after 40s")


class DnsReasonTests(unittest.TestCase):
    def domain(self, **run):
        with patch.object(dns.shutil, "which", return_value="/usr/bin/dig"), patch.object(
            dns.subprocess, "run", **run
        ):
            return dns._domain("example.net")

    def test_malformed_answer_is_named(self):
        env = self.domain(return_value=subprocess.CompletedProcess([], 0, "1 13 2 GG", ""))
        self.assertEqual(env["truth_state"], "UNAVAILABLE")
        self.assertEqual(env["reason"], "malformed or unsupported DS response from dig")

    def test_failed_dig_reports_exit_status_not_resolver_details(self):
        stderr = ";; communications error to " + LEAK + "#53: timed out"
        env = self.domain(return_value=subprocess.CompletedProcess([], 9, "", stderr))
        self.assertEqual(env["truth_state"], "UNAVAILABLE")
        self.assertEqual(env["reason"], "dig exited with status 9")

    def test_dig_timeout_reports_the_limit(self):
        env = self.domain(side_effect=subprocess.TimeoutExpired(["dig", LEAK], dns.DIG_TIMEOUT))
        self.assertEqual(env["reason"], f"timed out after {dns.DIG_TIMEOUT}s")


class HttpCollectorReasonTests(unittest.TestCase):
    def test_cloudflare_http_error_reports_status_without_url(self):
        with patch.object(cloudflare.requests, "get", return_value=http_response(403)):
            env = cloudflare._zone("a-11-oy.com", "dummy-token")
        self.assertEqual(env["truth_state"], "UNAVAILABLE")
        self.assertEqual(env["reason"], "Cloudflare API returned HTTP 403")

    def test_cloudflare_api_failure_reports_error_codes_not_messages(self):
        for errors, expected in (
            ([{"code": 10000, "message": LEAK}, {"code": 9109, "message": LEAK}],
             "Cloudflare API reported failure (error codes 9109, 10000)"),
            ([{"message": LEAK}], "Cloudflare API reported failure"),
            ([], "Cloudflare API reported failure"),
        ):
            with self.subTest(errors=errors):
                body = json.dumps({"success": False, "errors": errors}).encode()
                with patch.object(cloudflare.requests, "get", return_value=http_response(200, body)):
                    env = cloudflare._zone("a-11-oy.com", "dummy-token")
                self.assertEqual(env["reason"], expected)

    def test_cloudflare_transport_failure_is_named_by_kind(self):
        with patch.object(cloudflare.requests, "get", side_effect=requests.ConnectionError(LEAK)):
            env = cloudflare._zone("a-11-oy.com", "dummy-token")
        self.assertEqual(env["reason"], "ConnectionError")

    def test_huggingface_http_error_reports_status_without_url(self):
        with patch.dict(os.environ, {"HF_TOKEN": "dummy-token"}), patch.object(
            huggingface.requests, "get", return_value=http_response(401)
        ):
            env = huggingface.collect()
        self.assertEqual(env["truth_state"], "UNAVAILABLE")
        self.assertEqual(env["reason"], "Hugging Face API returned HTTP 401")


class ReceiptsReasonTests(unittest.TestCase):
    def test_verifier_timeout_and_unreadable_bundle_are_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = os.path.join(tmp, "self_audit_bundle.json")
            verifier = os.path.join(tmp, "a11oy_verify.py")
            for path, text in ((bundle, "not json " + LEAK), (verifier, "")):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            with patch.object(receipts, "BUNDLE", bundle), patch.object(receipts, "VERIFIER", verifier):
                with patch.object(
                    receipts.subprocess, "run",
                    side_effect=subprocess.TimeoutExpired(["python3", verifier, bundle], receipts.VERIFY_TIMEOUT),
                ):
                    run = receipts._run_verifier()
                facts = receipts._bundle_facts()
        self.assertEqual(run["reason"], f"timed out after {receipts.VERIFY_TIMEOUT}s")
        self.assertEqual(facts["reason"], "JSONDecodeError")


class ServedPayloadTests(unittest.TestCase):
    """The HTTP response is where CodeQL places the sink; check it there."""

    def failing_providers(self):
        # github and dns share the shutil and subprocess modules: patch each once.
        def which(name):
            return "/usr/bin/dig" if name == "dig" else None

        def run(args, **kwargs):
            if args[0] != "dig":
                raise AssertionError(f"unexpected subprocess: {args[0]}")
            return subprocess.CompletedProcess(args, 9, "", ";; communications error to " + LEAK)

        # cloudflare and huggingface share the requests module too.
        def get(url, **kwargs):
            if url.startswith(cloudflare.API):
                raise requests.ConnectionError(LEAK)
            if url.startswith(huggingface.API):
                return http_response(401)
            raise AssertionError(f"unexpected request: {url}")

        absent = os.path.join(tempfile.gettempdir(), "szl-absent-payloads")
        return (
            patch.object(main, "_response_cache", ResponseCache()),
            patch.object(receipts, "VERIFIER", os.path.join(absent, "a11oy_verify.py")),
            patch.object(receipts, "BUNDLE", os.path.join(absent, "self_audit_bundle.json")),
            patch.object(receipts, "MASTER", os.path.join(absent, "01-master")),
            patch.dict(os.environ, {"HF_TOKEN": "dummy-token", "CLOUDFLARE_API_TOKEN": "dummy-token"}),
            patch.object(github.shutil, "which", side_effect=which),
            patch.object(github.subprocess, "run", side_effect=run),
            patch.object(cloudflare.requests, "get", side_effect=get),
        )

    def request(self, route):
        with contextlib.ExitStack() as stack:
            for active in self.failing_providers():
                stack.enter_context(active)
            return route()

    def test_estate_route_serves_reasons_but_no_exception_text(self):
        response = self.request(main.api_estate)
        body = response.body.decode("utf-8")
        payload = json.loads(body)
        collectors = payload["collectors"]
        self.assertIn("gh CLI not found on PATH", collectors["github"]["reason"])
        self.assertEqual(collectors["dns"]["value"]["a-11-oy.com"]["reason"], "dig exited with status 9")
        self.assertEqual(collectors["cloudflare"]["value"]["a11oy.net"]["reason"], "ConnectionError")
        self.assertEqual(collectors["huggingface"]["reason"], "Hugging Face API returned HTTP 401")
        self.assertNotIn("LEAK", body)
        self.assertNotIn("SENTINEL", body)

    def test_verticals_route_serves_reasons_but_no_exception_text(self):
        response = self.request(main.api_verticals)
        body = response.body.decode("utf-8")
        payload = json.loads(body)
        for vertical in payload["verticals"]:
            self.assertEqual(vertical["truth_state"], "UNAVAILABLE")
            self.assertEqual(vertical["reason"], "gh CLI not found on PATH")
        self.assertNotIn("LEAK", body)

    def test_served_reasons_carry_no_urls_including_historical_snapshot(self):
        # evidence_ref names the source; a reason only says why it failed.
        for route in (main.api_estate, main.api_verticals):
            with self.subTest(route=route.__name__):
                payload = json.loads(self.request(route).body)
                self.assertIn("_historical_snapshot", payload)
                leaked = [path for path, reason in served_reasons(payload) if "://" in reason]
                self.assertEqual(leaked, [])


class CommittedSnapshotTests(unittest.TestCase):
    def test_baked_reasons_carry_no_urls(self):
        for name in ("estate.json", "verticals.json"):
            with self.subTest(snapshot=name):
                with open(os.path.join(SNAPSHOT_DIR, name), encoding="utf-8") as fh:
                    snapshot = json.load(fh)
                reasons = list(served_reasons(snapshot))
                self.assertTrue(reasons)
                self.assertEqual([path for path, reason in reasons if "://" in reason], [])


if __name__ == "__main__":
    unittest.main()

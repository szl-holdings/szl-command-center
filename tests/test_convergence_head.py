"""Bounded portable GitHub main-reader contract; no external HTTP in tests."""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from backend import convergence as cv


SHA = "a" * 40


def main_body(**overrides):
    doc = {"name": "main", "protected": True, "commit": {"sha": SHA}}
    doc.update(overrides)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


class MainReaderTests(unittest.TestCase):
    def setUp(self):
        self.reply = MagicMock()
        self.reply.status = 200
        self.reply.geturl.return_value = cv.GITHUB_MAIN_URL
        self.reply.headers.get.return_value = "application/json; charset=utf-8"
        self.reply.read.return_value = main_body()
        self.opener = MagicMock()
        self.opener.open.return_value.__enter__.return_value = self.reply
        self.patcher = patch.object(cv, "build_opener", return_value=self.opener)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_works_without_gh_binary_or_token(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(cv._head(), SHA)
        self.opener.open.assert_called_once()
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, cv.GITHUB_MAIN_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 10)
        self.reply.read.assert_called_once_with(cv.MAX_MAIN_RESPONSE + 1)

    def test_optional_auth_never_leaks_to_returned_revision(self):
        with patch.dict(os.environ, {"GH_TOKEN": "FAKE_TOKEN_1",
                                     "GITHUB_TOKEN": "FAKE_TOKEN_2"}, clear=True):
            result = cv._head()
        self.assertEqual(result, SHA)
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer FAKE_TOKEN_1")
        self.assertNotIn("FAKE_TOKEN_", result)

    def test_github_token_fallback_when_gh_token_absent(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "FAKE_TOKEN_2"}, clear=True):
            self.assertEqual(cv._head(), SHA)
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer FAKE_TOKEN_2")

    def test_branch_must_be_main_and_protected(self):
        for doc in [
            {"name": "other", "protected": True, "commit": {"sha": SHA}},
            {"name": "main", "protected": False, "commit": {"sha": SHA}},
            {"name": "main", "protected": "true", "commit": {"sha": SHA}},
            {"name": "main", "protected": True, "commit": {"sha": SHA[:7]}},
            {"name": "main", "protected": True, "commit": []},
        ]:
            with self.subTest(doc=doc):
                self.reply.read.return_value = json.dumps(doc).encode()
                with self.assertRaises(cv.InvalidObservation):
                    cv._head()

    def test_redirect_is_not_an_authenticated_observation(self):
        self.reply.geturl.return_value = "https://example.org/redirect"
        with self.assertRaisesRegex(cv.InvalidObservation, "REDIRECT_DENIED"):
            cv._head()

    def test_http_403_does_not_downgrade_to_anonymous(self):
        self.reply.status = 403
        with patch.dict(os.environ, {"GH_TOKEN": "FAKE_TOKEN_1"}, clear=True):
            with self.assertRaisesRegex(cv.InvalidObservation, "HTTP_OR_REDIRECT_DENIED"):
                cv._head()
        self.opener.open.assert_called_once()

    def test_malformed_or_duplicate_body_does_not_pass(self):
        for raw in [
            b'{"name":"main","name":"main","protected":true,"commit":{"sha":"' + SHA.encode() + b'"}}',
            b'{"name":"main","protected":true,"commit":null}',
            b'{"name":"main","protected":true,"commit":{"sha":null}}',
            b'[]',
            b'',
        ]:
            with self.subTest(raw=raw[:30]):
                self.reply.read.return_value = raw
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    cv._head()

    def test_bounded_and_typed_github_response(self):
        self.reply.read.return_value = b'x' * (cv.MAX_MAIN_RESPONSE + 1)
        with self.assertRaisesRegex(cv.InvalidObservation, "BODY_TOO_LARGE"):
            cv._head()
        self.reply.read.return_value = main_body()
        self.reply.headers.get.return_value = "text/html"
        with self.assertRaisesRegex(cv.InvalidObservation, "JSON_REQUIRED"):
            cv._head()

    def test_rate_status_is_safe_and_actionable_in_observation(self):
        from urllib.error import HTTPError
        for status in (403, 429):
            with self.subTest(status=status):
                def denied():
                    raise HTTPError(cv.GITHUB_MAIN_URL, status,
                                    "PRIVATE_DIAGNOSTIC_DO_NOT_EXPOSE",
                                    {"Authorization": "FAKE_TOKEN_1"}, None)
                def unavailable(_url):
                    raise OSError("PRIVATE_HTTP_ERROR_DO_NOT_EXPOSE")
                report = cv.collect(head_reader=denied, fetcher=unavailable,
                                    clock=lambda: "2026-11-17T05:40:00Z")
                self.assertEqual(report["source"]["state"], "UNKNOWN")
                self.assertFalse(report["observational_convergence"])
                self.assertIn("GITHUB_MAIN_BEFORE_HTTP_" + str(status),
                              report["blocker_codes"])
                self.assertIn("GITHUB_MAIN_AFTER_HTTP_" + str(status),
                              report["blocker_codes"])
                output = json.dumps(report)
                self.assertNotIn("PRIVATE_DIAGNOSTIC", output)
                self.assertNotIn("FAKE_TOKEN", output)

    def test_authenticated_rate_limit_has_no_unauthenticated_retry(self):
        from urllib.error import HTTPError
        self.opener.open.side_effect = HTTPError(cv.GITHUB_MAIN_URL, 403,
                                                  "rate limited", {}, None)
        with patch.dict(os.environ, {"GH_TOKEN": "FAKE_TOKEN_1"}, clear=True):
            with self.assertRaises(HTTPError):
                cv._head()
        self.opener.open.assert_called_once()


if __name__ == "__main__":
    unittest.main()

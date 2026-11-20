"""Independent, offline admission tests for Python-only operator frontend/backend."""
import base64
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main, unified_ops

USER = "localoperator"
PASS = "very-long-fake-password-not-a-real-secret"
HEAD = "f" * 40
SECRET_IN_DATA = "SHOULD_NEVER_BE_RENDERED_<>"
ENV = {
    "SZL_UNIFIED_OPS_READONLY_ENABLED": "1",
    "SZL_UNIFIED_OPS_USER": USER,
    "SZL_UNIFIED_OPS_PASSWORD": PASS,
}


def auth(name=USER, password=PASS):
    raw = f"{name}:{password}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def fixture_source(url):
    if url.startswith("https://api.github.com/repos/"):
        return {"name": "main", "protected": True, "commit": {"sha": HEAD}}
    if url.startswith("https://huggingface.co/api/spaces/"):
        name = url.split("/")[-1]
        return {"id": f"SZLHOLDINGS/{name}", "private": False, "sha": HEAD,
                "runtime": {"stage": "RUNNING"}}
    raise AssertionError("foreign URL: " + url)


class UnifiedOpsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.env = patch.dict(os.environ, ENV, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.public = patch.object(unified_ops.public_preview, "active", return_value=False)
        self.public.start()
        self.addCleanup(self.public.stop)
        # Cache must be isolated per test so no cached private snapshot is reused.
        self.cache = patch.object(unified_ops, "CACHE", unified_ops.ResponseCache(0))
        self.cache.start()
        self.addCleanup(self.cache.stop)

    def test_disabled_blocks_before_any_provider_read(self):
        with patch.dict(os.environ, {"SZL_UNIFIED_OPS_READONLY_ENABLED": "0"}), \
             patch.object(unified_ops, "_public_get", side_effect=AssertionError("provider")):
            resp = self.client.get("/api/ops/unified", headers=auth())
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["reason"], "OPERATOR_SURFACE_NOT_ADMITTED")

    def test_public_preview_overrides_enable_and_credentials(self):
        with patch.object(unified_ops.public_preview, "active", return_value=True), \
             patch.object(unified_ops, "_public_get", side_effect=AssertionError("provider")):
            resp = self.client.get("/ops/unified", headers=auth())
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["reason"], "PUBLIC_PREVIEW_OPERATOR_SURFACE_DENIED")

    def test_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {"SZL_UNIFIED_OPS_PASSWORD": ""}), \
             patch.object(unified_ops, "_public_get", side_effect=AssertionError("provider")):
            resp = self.client.get("/api/ops/unified", headers=auth())
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["reason"], "OPERATOR_CREDENTIAL_NOT_CONFIGURED")

    def test_no_auth_is_challenged_before_provider(self):
        with patch.object(unified_ops, "_public_get", side_effect=AssertionError("provider")):
            resp = self.client.get("/ops/unified")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.headers["cache-control"], "no-store")
        self.assertIn("Basic", resp.headers["www-authenticate"])

    def test_wrong_password_denies_provider(self):
        with patch.object(unified_ops, "_public_get", side_effect=AssertionError("provider")):
            resp = self.client.get("/api/ops/unified", headers=auth(password="wrong"))
        self.assertEqual(resp.status_code, 401)

    def test_forwarded_remote_headers_denied(self):
        with patch.object(unified_ops, "_public_get", side_effect=AssertionError("provider")):
            resp = self.client.get("/api/ops/unified",
                                   headers={**auth(), "X-Forwarded-For": "8.8.8.8"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["reason"], "LOCAL_ORIGIN_REQUIRED")

    def test_bogus_basic_header_is_not_accepted(self):
        for value in ("Bearer garbage", "Basic !!not-base64!!", "Basic " + "A"*800):
            with self.subTest(value=value[:20]):
                resp = self.client.get("/api/ops/unified",
                                       headers={"Authorization": value})
                self.assertEqual(resp.status_code, 401)

    def test_authenticated_snapshot_current_owned_sources(self):
        with patch.object(unified_ops, "_public_get", side_effect=fixture_source):
            response = self.client.get("/api/ops/unified", headers=auth())
        self.assertEqual(response.status_code, 200)
        j = response.json()
        self.assertEqual(j["owner"], "szl-holdings")
        self.assertEqual(j["source_repos_observed"], 8)
        self.assertEqual(len(j["compute_pools"]), 4)
        self.assertFalse(j["can_deploy"])
        self.assertFalse(j["production_admitted"])
        self.assertEqual(j["services"][1]["source_sha"], HEAD)
        self.assertEqual(j["services"][1]["provider_stage"], "RUNNING")
        self.assertFalse(j["services"][1]["authenticated_render"])
        self.assertEqual(response.headers["x-robots-tag"], "noindex")
        self.assertNotIn(PASS, response.text)

    def test_python_frontend_render_and_controls(self):
        with patch.object(unified_ops, "_public_get", side_effect=fixture_source):
            response = self.client.get("/ops/unified", headers=auth())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/html"))
        for phrase in ("Unified control plane", "Separate", "/ops/unified/plan",
                       "HOLD", "szl-gpu-bridge", "provider"):
            self.assertIn(phrase.lower(), response.text.lower())
        self.assertNotIn(PASS, response.text)
        self.assertIn("default-src 'none'", response.headers["content-security-policy"])

    def test_untrusted_fields_html_escaped(self):
        base = {
            "owner": "szl-holdings", "observed_at": "now",
            "source_repos_observed": 0, "source_repos_total": 1,
            "services": [], "compute_pools": [],
        }
        base["services"] = [{
            "name": "<script>payload()</script>", "kind": "test", "repository": "a11oy",
            "source_url": "https://github.com/szl-holdings/a11oy",
            "source_state": "UNKNOWN", "source_reason": "untrusted <img src=x>",
            "source_sha": None, "runtime_state": "UNAVAILABLE",
            "provider_stage": None
        }]
        html = unified_ops.render(base)
        self.assertNotIn("<script>payload()", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img src=x&gt;", html)

    def test_missing_git_identity_unknown_not_verified(self):
        with patch.object(unified_ops, "_public_get", side_effect=lambda _: {
            "name": "main", "protected": False, "commit": {"sha": HEAD}}):
            row = unified_ops.source_row(("X", "a11oy", None, "test"))
        self.assertEqual(row["source_state"], "UNKNOWN")
        self.assertFalse(row["production_admitted"])


    def test_staging_public_visibility_is_visible_but_not_authorized(self):
        with patch.object(unified_ops, "_public_get", side_effect=fixture_source):
            response = self.client.get("/api/ops/unified", headers=auth())
        self.assertEqual(response.json()["staging_visibility"]["state"], "DRIFT")
        self.assertFalse(response.json()["staging_visibility"]["production_admitted"])
        with patch.object(unified_ops, "_public_get", side_effect=fixture_source):
            page = self.client.get("/ops/unified", headers=auth())
        self.assertIn("STAGING_DECLARED_PRIVATE_BUT_PUBLIC", page.text)

    def test_spoofed_local_host_with_remote_peer_is_denied(self):
        from starlette.requests import Request as StarletteRequest
        scope = {"type": "http", "method": "GET", "scheme": "http",
                 "path": "/api/ops/unified", "root_path": "", "query_string": b"",
                 "headers": [(b"host", b"127.0.0.1")],
                 "client": ("203.0.113.7", 5200), "server": ("127.0.0.1", 8707)}
        req = StarletteRequest(scope)
        self.assertFalse(unified_ops._is_local_request(req))
        result = unified_ops._operator_gate(req)
        self.assertIsNotNone(result)
        self.assertEqual(result.status_code, 403)

    def test_server_bound_to_all_interfaces_is_denied_even_with_local_peer(self):
        from starlette.requests import Request as StarletteRequest
        scope = {"type": "http", "method": "GET", "scheme": "http",
                 "path": "/api/ops/unified", "root_path": "", "query_string": b"",
                 "headers": [(b"host", b"localhost")],
                 "client": ("127.0.0.1", 5200), "server": ("0.0.0.0", 8000)}
        self.assertFalse(unified_ops._is_local_request(StarletteRequest(scope)))

    def test_sha_validator_exists_and_rejects_near_miss(self):
        self.assertIsNotNone(unified_ops.SHA40.fullmatch(HEAD))
        self.assertIsNone(unified_ops.SHA40.fullmatch("g" * 40))
        self.assertIsNone(unified_ops.SHA40.fullmatch(HEAD + "x"))

    def test_malformed_nested_git_commit_does_not_crash_or_verify(self):
        with patch.object(unified_ops, "_public_get",
                          return_value={"name": "main", "protected": True,
                                        "commit": "invalid"}):
            row = unified_ops.source_row(("broken", "a11oy", None, "test"))
        self.assertEqual(row["source_state"], "UNKNOWN")

    def test_html_link_disallows_wrong_url_scheme(self):
        base = {"owner": "szl-holdings", "observed_at": "now",
                "source_repos_observed": 0, "source_repos_total": 1,
                "services": [{"name": "X", "kind": "test", "repository": "a11oy",
                              "source_url": "javascript:alert(1)",
                              "source_sha": None, "source_state": "UNKNOWN",
                              "source_reason": "NO_SOURCE", "runtime_state": "UNKNOWN",
                              "provider_stage": None}], "compute_pools": []}
        text = unified_ops.render(base)
        self.assertNotIn("javascript:", text)
        self.assertIn("https://github.com/szl-holdings", text)

    def test_unsigned_job_plan_never_dispatches(self):
        plan = {"pool": "salad", "repository": "a11oy", "source_sha": HEAD,
                "workload": "evaluation"}
        with patch.object(unified_ops, "_public_get", side_effect=AssertionError("provider")):
            response = self.client.post("/api/ops/unified/plan", headers=auth(),
                                        json=plan)
        self.assertEqual(response.status_code, 200)
        j = response.json()
        self.assertEqual(j["state"], "HOLD")
        self.assertEqual(len(j["plan_sha256"]), 64)
        self.assertFalse(j["job_submitted"])
        self.assertFalse(j["persisted"])
        self.assertFalse(j["provider_invoked"])

    def test_pseudo_job_is_not_accepted_for_laptop(self):
        plan = {"pool": "betterwithage", "repository": "a11oy",
                "source_sha": HEAD, "workload": "inference"}
        response = self.client.post("/api/ops/unified/plan", json=plan, headers=auth())
        self.assertEqual(response.status_code, 400)

    def test_duplicate_json_key_fails_closed(self):
        raw = ('{"pool":"salad","pool":"massed","repository":"a11oy",'
               '"source_sha":"' + HEAD + '","workload":"evaluation"}')
        response = self.client.post("/api/ops/unified/plan",
            content=raw, headers={**auth(), "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 400)

    def test_unknown_plan_and_extra_keys_rejected(self):
        for payload in (
            {"pool": "salad", "repository": "someone-else", "source_sha": HEAD,
             "workload": "training"},
            {"pool": "salad", "repository": "a11oy", "source_sha": HEAD,
             "workload": "training", "secret": "DONT_ACCEPT"},
            {"pool": "salad", "repository": "a11oy", "source_sha": "invalid",
             "workload": "training"},
        ):
            with self.subTest(payload=payload):
                response = self.client.post("/api/ops/unified/plan",
                                            json=payload, headers=auth())
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("DONT_ACCEPT", response.text)

    def test_body_limit_denies_large_request(self):
        response = self.client.post("/api/ops/unified/plan",
                                    content=b"x" * 8000,
                                    headers={**auth(), "Content-Type": "application/json"})
        self.assertEqual(response.status_code, 400)

    def test_dispatch_is_explicitly_forbidden(self):
        response = self.client.post("/api/ops/unified/dispatch", headers=auth())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["dispatched"])

    def test_html_form_returns_hold_receipt(self):
        payload = {"pool": "massed", "repository": "szl-command-center",
                   "source_sha": HEAD, "workload": "batch"}
        with patch.object(unified_ops, "_public_get", side_effect=fixture_source):
            response = self.client.post("/ops/unified/plan", data=payload,
                                        headers=auth())
        self.assertEqual(response.status_code, 200)
        self.assertIn("Job plan: HOLD", response.text)
        self.assertIn("No queue", response.text)

    def test_existing_health_and_frontend_are_untouched(self):
        health = self.client.get("/api/health")
        static = self.client.get("/")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(static.status_code, 200)
        self.assertIn("html", static.headers["content-type"])


if __name__ == "__main__":
    unittest.main()

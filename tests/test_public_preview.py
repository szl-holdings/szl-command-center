"""Fail-closed public-preview isolation of provider-backed private collectors.

Public Docker deployments may have accidental environment tokens. This suite
proves the public API never invokes those legacy collectors, even with tokens.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main, public_preview
from backend.verticals import VERTICALS


class PreviewBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.marker = self.root / "source_manifest.json"
        self.p = patch.object(public_preview, "DEPLOYED_MANIFEST", self.marker)
        self.p.start()
        self.addCleanup(self.p.stop)

    def test_local_non_deployed_source_is_not_misclassified(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(public_preview.active())

    def test_deployed_source_marker_forces_public_even_if_env_overridden(self):
        self.marker.write_text("anything")
        with patch.dict(os.environ, {"SZL_COMMAND_CENTER_MODE": "private_ops"},
                        clear=True):
            self.assertTrue(public_preview.active())

    def test_explicit_public_mode_without_marker(self):
        with patch.dict(os.environ, {"SZL_COMMAND_CENTER_MODE": "public_preview"},
                        clear=True):
            self.assertTrue(public_preview.active())

    def test_privileged_tokens_cannot_activate_private_collector_on_public_api(self):
        self.marker.write_text("{}")
        env = {
            "SZL_COMMAND_CENTER_MODE": "private_ops",
            "GH_TOKEN": "NEVER_EXPOSE_GITHUB_TOKEN",
            "HF_TOKEN": "NEVER_EXPOSE_HF_TOKEN",
            "CLOUDFLARE_API_TOKEN": "NEVER_EXPOSE_CLOUDFLARE_TOKEN",
            "SZL_ONTOLOGY_READONLY_ENABLED": "1",
        }
        with patch.dict(os.environ, env, clear=True), \
             patch.object(main.github, "collect", side_effect=AssertionError("github invoked")), \
             patch.object(main.huggingface, "collect", side_effect=AssertionError("hf invoked")), \
             patch.object(main.cloudflare, "collect", side_effect=AssertionError("cf invoked")), \
             patch.object(main.dns, "collect", side_effect=AssertionError("dns invoked")), \
             patch.object(main.receipts, "collect", side_effect=AssertionError("verifier invoked")), \
             patch.object(main.verticals_mod, "collect", side_effect=AssertionError("verticals invoked")), \
             patch.object(main, "_cached", side_effect=AssertionError("prior cache consulted")), \
             patch.object(main, "_snapshot", side_effect=AssertionError("historical snapshot consulted")):
            client = TestClient(main.app)
            estate = client.get("/api/estate")
            vertical = client.get("/api/verticals")
            ontology = client.get("/api/ontology")
        for reply in (estate, vertical, ontology):
            self.assertEqual(reply.status_code, 200)
            self.assertEqual(reply.headers["cache-control"], "no-store")
            self.assertNotIn("NEVER_EXPOSE_", reply.text)
            self.assertNotIn("_historical_snapshot", reply.text)
        result = estate.json()
        self.assertEqual(result["scope"], "public_preview")
        self.assertEqual(result["summary"]["panels_verified"], 0)
        self.assertEqual(result["summary"]["panels_total"], 5)
        self.assertEqual(set(result["collectors"]), set(public_preview.COLLECTORS))
        self.assertTrue(all(
            env["truth_state"] == "UNAVAILABLE"
            and env["value"] is None
            and env["reason"] == public_preview.REASON
            for env in result["collectors"].values()
        ))
        self.assertEqual(vertical.json()["scope"], "public_preview")
        self.assertEqual(len(vertical.json()["verticals"]), len(VERTICALS))
        self.assertTrue(all(
            row["truth_state"] == "UNAVAILABLE" and row["value"]["health"] == "unknown"
            and row["value"]["open_issues"] is None
            for row in vertical.json()["verticals"]
        ))
        proof = ontology.json()
        self.assertEqual(proof["verified_sources"], 0)
        self.assertEqual(proof["rollup"], "UNAVAILABLE")
        self.assertFalse(proof["authorization"]["can_execute_actions"])

    def test_public_snapshot_does_not_claim_zero_repos_or_issues(self):
        result = public_preview.verticals()
        for row, source in zip(result["verticals"], VERTICALS):
            self.assertEqual(row["truth_state"], "UNAVAILABLE")
            self.assertEqual(len(row["value"]["repos"]), len(source["repos"]))
            self.assertIsNone(row["value"]["open_issues"])
            for repo in row["value"]["repos"]:
                self.assertEqual(repo["truth_state"], "UNAVAILABLE")
                self.assertIsNone(repo["latest_run"])
                self.assertFalse(repo["workflow_rollup"]["protected_merge_readiness"])

    def test_ontology_feature_disabled_remains_disabled(self):
        self.marker.write_text("anything")
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(main, "_cached", side_effect=AssertionError("cached")):
            response = main.api_ontology()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body)["reason_code"], "FEATURE_NOT_ADMITTED")


if __name__ == "__main__":
    unittest.main()

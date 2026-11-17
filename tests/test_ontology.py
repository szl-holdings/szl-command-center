import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend.ontology import project
from backend import main

NOW = datetime(2026, 11, 16, 23, 40, tzinfo=timezone.utc)


def estate(**overrides):
    collectors = {name: {
        "truth_state": "VERIFIED",
        "verified_at": "2026-11-16T23:39:50Z",
        "evidence_ref": "https://example.invalid/" + name,
        "value": {"token": "SENSITIVE_DO_NOT_EXPOSE", "detail": "raw"},
    } for name in ("github", "huggingface", "cloudflare", "dns", "receipts")}
    collectors.update(overrides)
    return {"collectors": collectors, "generated_at": "2026-11-16T23:39:50Z"}


class OntologyContractTests(unittest.TestCase):
    def test_complete_fresh_snapshot_projection(self):
        out = project(estate(), now=NOW)
        self.assertEqual(out["rollup"], "VERIFIED")
        self.assertEqual(out["verified_sources"], 5)
        self.assertEqual(len(out["links"]), 5)
        self.assertFalse(out["authorization"]["can_execute_actions"])
        self.assertEqual(out["provenance"]["snapshot_signature"], "NOT_ESTABLISHED")
        self.assertNotIn("SENSITIVE_DO_NOT_EXPOSE", json.dumps(out))
        self.assertNotIn("example.invalid", json.dumps(out))

    def test_missing_and_mixed_fail_closed(self):
        out = project({"collectors": {"github": {}}}, now=NOW)
        self.assertEqual(out["rollup"], "UNAVAILABLE")
        self.assertEqual(out["verified_sources"], 0)
        self.assertEqual(len(out["nodes"]), 6)

    def test_stale_verified_degrades(self):
        e = estate()
        e["collectors"]["github"]["verified_at"] = "2026-11-16T20:00:00Z"
        out = project(e, now=NOW)
        self.assertEqual(out["rollup"], "UNKNOWN")
        self.assertEqual(out["nodes"][1]["reason_code"], "OBSERVATION_STALE_OR_INVALID")

    def test_missing_evidence_identity_degrades(self):
        e = estate()
        e["collectors"]["github"]["evidence_ref"] = ""
        out = project(e, now=NOW)
        self.assertEqual(out["nodes"][1]["truth_state"], "UNKNOWN")

    def test_future_observation_degrades(self):
        e = estate()
        e["collectors"]["github"]["verified_at"] = "2026-11-17T00:00:00Z"
        self.assertEqual(project(e, now=NOW)["rollup"], "UNKNOWN")

    def test_invalid_state_fails_closed(self):
        e = estate()
        e["collectors"]["github"]["truth_state"] = "APPROVED"
        self.assertEqual(project(e, now=NOW)["nodes"][1]["truth_state"], "UNAVAILABLE")

    def test_nonstring_unhashable_truth_state_denied_without_exception(self):
        e = estate()
        e["collectors"]["github"]["truth_state"] = ["VERIFIED"]
        out = project(e, now=NOW)
        self.assertEqual(out["nodes"][1]["truth_state"], "UNAVAILABLE")
        self.assertNotEqual(out["rollup"], "VERIFIED")

    def test_whitespace_evidence_identity_downgrades(self):
        e = estate()
        e["collectors"]["github"]["evidence_ref"] = "  "
        out = project(e, now=NOW)
        self.assertEqual(out["nodes"][1]["truth_state"], "UNKNOWN")
        self.assertIsNone(out["nodes"][1]["evidence_ref_sha256"])

    def test_checksum_deterministic_and_tamper_visible(self):
        first = project(estate(), now=NOW)
        second = project(estate(), now=NOW)
        self.assertEqual(first["content_sha256"], second["content_sha256"])
        altered = estate()
        altered["collectors"]["github"]["truth_state"] = "UNKNOWN"
        self.assertNotEqual(first["content_sha256"], project(altered, now=NOW)["content_sha256"])

    def test_default_disabled_does_not_collect_or_publish(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(main, "_cached") as cache:
            response = main.api_ontology()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body)["reason_code"], "FEATURE_NOT_ADMITTED")
        self.assertEqual(response.headers["cache-control"], "no-store")
        cache.assert_not_called()

    def test_snapshot_freshness_overrides_upstream_verified(self):
        e = estate()
        e["generated_at"] = "2026-11-15T12:00:00Z"
        out = project(e, now=NOW)
        self.assertEqual(out["verified_sources"], 0)
        self.assertEqual(out["rollup"], "UNKNOWN")
        self.assertEqual(out["nodes"][1]["reason_code"], "SNAPSHOT_STALE_OR_INVALID")

    def test_graph_binds_source_snapshot(self):
        e = estate()
        first = project(e, now=NOW)
        self.assertEqual(first["source_generated_at"], e["generated_at"])
        self.assertEqual(len(first["source_snapshot_sha256"]), 64)
        modified = estate()
        modified["generated_at"] = "2026-11-16T23:39:49Z"
        other = project(modified, now=NOW)
        self.assertNotEqual(first["source_snapshot_sha256"], other["source_snapshot_sha256"])

    def test_untrusted_values_are_never_projected(self):
        e = estate()
        e["collectors"]["github"]["value"] = {"model_prompt": "PRIVATE_FIELD_SHOULD_NOT_BE_PUBLIC"}
        out = project(e, now=NOW)
        text = json.dumps(out)
        self.assertNotIn("PRIVATE_FIELD_SHOULD_NOT_BE_PUBLIC", text)
        self.assertNotIn("example.invalid", text)

    def test_route_uses_existing_cache_without_extra_collector(self):
        snapshot = estate()
        with patch.dict(os.environ, {"SZL_ONTOLOGY_READONLY_ENABLED": "1"}), patch.object(main, "_cached", return_value=snapshot) as cache:
            response = main.api_ontology()
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["schema"], "szl.readonly.evidence_graph.v1")
        self.assertFalse(body["authorization"]["can_execute_actions"])
        cache.assert_called_once()
        self.assertEqual(cache.call_args.args[0], "estate")


if __name__ == "__main__":
    unittest.main()

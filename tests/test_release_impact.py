"""Adversarial release-impact tests: scope, DAG, monotonicity, privacy, API gate."""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend import main, ontology, release_fabric, release_impact

NOW = datetime.now(timezone.utc).replace(microsecond=0)
STAMP = NOW.isoformat()
SOURCES = release_impact.SELECTABLE
STATES = ("VERIFIED", "UNKNOWN", "UNAVAILABLE")


def estate(states=None):
    states = states or {}
    return {
        "generated_at": STAMP,
        "collectors": {
            name: {
                "truth_state": states.get(name, "VERIFIED"),
                "verified_at": STAMP,
                "evidence_ref": "opaque:fixture-only-" + name,
                "value": {
                    "private_customer": "DO_NOT_EXPORT_PII",
                    "model_input": "DO_NOT_EXPORT_PROMPT",
                    "payment": {"signature": "DO_NOT_EXPORT_SIGNATURE"},
                },
            } for name in SOURCES
        },
    }


def graph(states=None):
    return ontology.project(estate(states), now=NOW)


class ImpactContracts(unittest.TestCase):
    def test_no_authority_all_1215_collector_combinations(self):
        for value in itertools.product(STATES, repeat=len(SOURCES)):
            record = graph(dict(zip(SOURCES, value)))
            for name in SOURCES:
                result = release_impact.simulate(record, name, record["source_snapshot_sha256"])
                self.assertEqual(result["schema"], release_impact.SCHEMA)
                for forbidden in ("can_deploy", "production_qualified", "action_authorized",
                                  "provider_state_changed", "model_quality_verified",
                                  "settlement_verified", "fingerprint_is_signature"):
                    self.assertIs(result[forbidden], False, forbidden)
                self.assertEqual(result["required_proof_state"], "NOT_ESTABLISHED")
                self.assertEqual(result["basis_source_snapshot_sha256"], record["source_snapshot_sha256"])
                self.assertEqual(result["basis_release_fabric_sha256"],
                                 record["release_fabric"]["content_sha256"])
                for x in result["collector_stage_changes"]:
                    self.assertIn(x["before"], STATES)
                    self.assertIn(x["after"], STATES)
                    self.assertNotEqual(x["before"], "UNAVAILABLE")
                    self.assertNotEqual(x["after"], "VERIFIED")
                self.assertEqual(result["collector_changes_count"],
                                 len(result["collector_stage_changes"]))
                self.assertEqual(result["exposed_stage_count"],
                                 len(result["structurally_exposed_stages"]))
                self.assertLessEqual(result["exposed_stage_count"], 8)
                self.assertLessEqual(len(result["structurally_exposed_edges"]), 9)
                self.assertTrue(all(not edge["binding_verified"]
                                    for edge in result["structurally_exposed_edges"]))

    def test_scenarios_are_deterministic_and_source_bound(self):
        record = graph()
        a = release_impact.simulate(record, "github", record["source_snapshot_sha256"])
        b = release_impact.simulate(record, "github", record["source_snapshot_sha256"])
        self.assertEqual(a, b)
        body = {k: v for k, v in a.items() if k != "content_sha256"}
        self.assertEqual(a["content_sha256"], hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest())
        self.assertNotEqual(
            release_impact.simulate(graph({"github": "UNKNOWN"}), "github",
                                    graph({"github": "UNKNOWN"})["source_snapshot_sha256"])["content_sha256"],
            a["content_sha256"],
        )

    def test_direct_and_structural_impact_are_distinct(self):
        record = graph()
        github = release_impact.simulate(record, "github", record["source_snapshot_sha256"])
        self.assertEqual([x["stage"] for x in github["collector_stage_changes"]],
                         ["github_source"])
        self.assertEqual(github["structurally_exposed_stages"],
                         ["github_source", "hf_catalog", "cloudflare_edge",
                          "model_evaluation", "runtime_deployment",
                          "payment_settlement", "pypi_distribution"])
        self.assertNotIn("receipt_index", github["structurally_exposed_stages"])
        cf = release_impact.simulate(record, "cloudflare", record["source_snapshot_sha256"])
        self.assertEqual(cf["collector_stage_changes"],
                         [{"stage": "cloudflare_edge", "before": "VERIFIED",
                           "after": "UNKNOWN"}])
        self.assertEqual(cf["structurally_exposed_stages"],
                         ["cloudflare_edge", "runtime_deployment", "payment_settlement"])
        receipt = release_impact.simulate(record, "receipts", record["source_snapshot_sha256"])
        self.assertEqual(receipt["structurally_exposed_stages"],
                         ["receipt_index", "model_evaluation", "payment_settlement"])

    def test_already_unavailable_does_not_claim_new_loss(self):
        record = graph({"github": "UNAVAILABLE"})
        a = release_impact.simulate(record, "github", record["source_snapshot_sha256"])
        self.assertFalse(a["observation_changed"])
        self.assertEqual(a["collector_stage_changes"], [])
        self.assertGreater(a["exposed_stage_count"], 0)
        self.assertFalse(a["production_qualified"])

    def test_reject_wrong_basis_identity_and_tampering(self):
        record = graph()
        for source, basis in [
            ("not-a-source", record["source_snapshot_sha256"]),
            (["github"], record["source_snapshot_sha256"]),
            ("github", "main"),
            ("github", "A" * 64),
            ("github", "f" * 64),
        ]:
            with self.subTest(source=source, basis=str(basis)), self.assertRaises(ValueError):
                release_impact.simulate(record, source, basis)
        mutated = copy.deepcopy(record)
        mutated["release_fabric"]["stages"][0]["qualification"] = "QUALIFIED"
        with self.assertRaisesRegex(ValueError, "RELEASE_FABRIC_STAGE_INVALID"):
            release_impact.simulate(mutated, "github", mutated["source_snapshot_sha256"])
        mutated = copy.deepcopy(record)
        mutated["release_fabric"]["dependencies"][0]["evidence_state"] = "VERIFIED"
        with self.assertRaisesRegex(ValueError, "EDGE_INVALID"):
            release_impact.simulate(mutated, "github", mutated["source_snapshot_sha256"])
        mutated = copy.deepcopy(record)
        mutated["release_fabric"]["collector_verified_stages"] = 99
        with self.assertRaisesRegex(ValueError, "DIGEST_MISMATCH"):
            release_impact.simulate(mutated, "github", mutated["source_snapshot_sha256"])

    def test_cycle_or_backward_dependency_refused_not_derived(self):
        broken = tuple(release_fabric.EDGES) + (
            ("payment_settlement", "github_source", "INVENTED_RETURN"),
        )
        with patch.object(release_fabric, "EDGES", broken):
            with self.assertRaisesRegex(ValueError, "BACKWARD_EDGE"):
                release_impact._closure(["github_source"])

    def test_no_private_collector_values_or_sources_in_output(self):
        r = graph()
        s = json.dumps(release_impact.simulate(r, "github", r["source_snapshot_sha256"]))
        for forbidden in ("DO_NOT_EXPORT_PII", "DO_NOT_EXPORT_PROMPT",
                          "DO_NOT_EXPORT_SIGNATURE", "opaque:fixture"):
            self.assertNotIn(forbidden, s)

    def test_disabled_route_does_not_touch_collectors(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(main, "_cached") as cached:
            resp = main.api_release_impact("github", "a" * 64)
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(json.loads(resp.body)["reason_code"], "FEATURE_NOT_ADMITTED")
        self.assertEqual(resp.headers["cache-control"], "no-store")
        cached.assert_not_called()

    def test_bad_request_rejected_before_provider_or_cache(self):
        with patch.dict(os.environ, {"SZL_ONTOLOGY_READONLY_ENABLED": "1"}), patch.object(
            main, "_cached"
        ) as cached:
            resp = main.api_release_impact("unknown", "a" * 64)
            bad_sha = main.api_release_impact("github", "main")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(bad_sha.status_code, 400)
        cached.assert_not_called()

    def test_route_reads_one_shared_existing_cache_and_rejects_other_basis(self):
        e = estate()
        basis = graph()["source_snapshot_sha256"]
        with patch.dict(os.environ, {"SZL_ONTOLOGY_READONLY_ENABLED": "1"}), patch.object(
            main.public_preview, "active", return_value=False
        ), patch.object(main, "_cached", return_value=e) as cached:
            resp = main.api_release_impact("github", basis)
            changed = main.api_release_impact("github", "f" * 64)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(json.loads(resp.body)["action_authorized"])
        self.assertEqual(resp.headers["cache-control"], "no-store")
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(json.loads(changed.body)["reason_code"], "SOURCE_SNAPSHOT_CHANGED")
        self.assertEqual(cached.call_count, 2)
        self.assertEqual(cached.call_args.args[0], "estate")

    def test_real_asgi_route_status_codes_and_exact_wire_body(self):
        from fastapi.testclient import TestClient
        client = TestClient(main.app)
        e = estate()
        basis = graph()["source_snapshot_sha256"]
        with patch.dict(os.environ, {"SZL_ONTOLOGY_READONLY_ENABLED": "1"}), patch.object(
            main.public_preview, "active", return_value=False
        ), patch.object(main, "_cached", return_value=e) as cached:
            good = client.get("/api/release-impact", params={"source": "github", "basis": basis})
            stale = client.get("/api/release-impact", params={"source": "github",
                                                             "basis": "f" * 64})
            bad = client.get("/api/release-impact", params={"source": "../",
                                                           "basis": basis})
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.headers["cache-control"], "no-store")
        self.assertEqual(good.headers["x-robots-tag"], "noindex")
        self.assertEqual(good.json()["exposed_stage_count"], 7)
        self.assertFalse(good.json()["can_deploy"])
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(cached.call_count, 2, "bad sources must not read collectors")
        with patch.dict(os.environ, {}, clear=True), patch.object(main, "_cached") as cached:
            denied = client.get("/api/release-impact", params={
                "source": "github", "basis": basis})
        self.assertEqual(denied.status_code, 503)
        self.assertEqual(denied.json()["reason_code"], "FEATURE_NOT_ADMITTED")
        cached.assert_not_called()

    def test_mutated_observation_state_does_not_bypass_fabric_contract(self):
        original = graph()
        tampered = copy.deepcopy(original)
        tampered["nodes"][1]["truth_state"] = "UNAVAILABLE"
        with self.assertRaisesRegex(ValueError, "RELEASE_FABRIC_STAGE_INVALID"):
            release_impact.simulate(tampered, "github",
                                    tampered["source_snapshot_sha256"])

    def test_public_preview_never_reads_privileged_cache(self):
        public = estate({name: "UNAVAILABLE" for name in SOURCES})
        basis = ontology.project(public, now=NOW)["source_snapshot_sha256"]
        with patch.dict(os.environ, {"SZL_ONTOLOGY_READONLY_ENABLED": "1"}), patch.object(
            main.public_preview, "active", return_value=True
        ), patch.object(main, "_public_preview_estate", return_value=public) as preview, patch.object(
            main, "_cached"
        ) as private:
            response = main.api_release_impact("huggingface", basis)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(json.loads(response.body)["observation_changed"])
        preview.assert_called_once()
        private.assert_not_called()


if __name__ == "__main__":
    unittest.main()

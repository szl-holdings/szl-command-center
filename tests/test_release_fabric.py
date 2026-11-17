"""Release-fabric acceptance: a collector read can never certify a release gate."""

import hashlib
import itertools
import json
import unittest
from datetime import datetime, timezone

from backend import release_fabric
from backend.ontology import project as project_ontology

NOW = datetime(2026, 11, 17, 23, 35, tzinfo=timezone.utc)
STAMP = "2026-11-17T23:34:51Z"
ALL = ("github", "huggingface", "cloudflare", "dns", "receipts")


def estate(states=None):
    states = states or {}
    return {
        "generated_at": STAMP,
        "collectors": {
            name: {
                "truth_state": states.get(name, "VERIFIED"),
                "verified_at": STAMP,
                "evidence_ref": "opaque:synthetic-evidence-" + name,
                "value": {
                    "secret": "NEVER_EXPORT_THIS",
                    "raw_payment_signature": "NOT_AN_ACTUAL_SIGNATURE",
                    "customer_id": "PRIVATE_FIXTURE_ID",
                },
            }
            for name in ALL
        },
    }


class ReleaseFabricTests(unittest.TestCase):
    def test_all_successful_collectors_do_not_qualify_any_release_stage(self):
        ontology = project_ontology(estate(), now=NOW)
        fabric = ontology["release_fabric"]
        self.assertEqual(fabric["schema"], release_fabric.SCHEMA)
        self.assertEqual(fabric["stage_count"], 8)
        self.assertEqual(fabric["collector_verified_stages"], 4)
        self.assertEqual(fabric["independently_qualified_stages"], 0)
        self.assertEqual(fabric["unverified_dependency_count"], 9)
        self.assertEqual(len(fabric["dependencies"]), 9)
        self.assertFalse(fabric["production_qualified"])
        self.assertFalse(fabric["can_deploy"])
        self.assertFalse(fabric["financial_revenue_verified"])
        self.assertFalse(fabric["fingerprint_is_signature"])
        self.assertEqual(fabric["basis_source_snapshot_sha256"], ontology["source_snapshot_sha256"])
        self.assertTrue(
            all(
                stage["qualification"] == "NOT_ESTABLISHED" and stage["can_execute_actions"] is False
                for stage in fabric["stages"]
            )
        )
        by_id = {s["id"]: s for s in fabric["stages"]}
        for no_collector in ("model_evaluation", "runtime_deployment", "payment_settlement", "pypi_distribution"):
            self.assertEqual(by_id[no_collector]["collector_state"], "UNAVAILABLE")
            self.assertEqual(by_id[no_collector]["collector_scope"], "NO_ADMITTED_COLLECTOR")
        self.assertEqual(by_id["cloudflare_edge"]["collectors"], ["cloudflare", "dns"])

    def test_exact_stages_edges_and_deterministic_checksum(self):
        first = project_ontology(estate(), now=NOW)
        other = project_ontology(estate(), now=NOW)
        self.assertEqual(first["release_fabric"], other["release_fabric"])
        graph = first["release_fabric"]
        sha = graph.pop("content_sha256")
        self.assertEqual(
            sha,
            hashlib.sha256(
                json.dumps(graph, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest(),
        )
        self.assertEqual(
            [(e["source"], e["target"], e["required_binding"]) for e in graph["dependencies"]],
            list(release_fabric.EDGES),
        )
        self.assertEqual([v["id"] for v in graph["stages"]], list(release_fabric.SOURCE_BINDINGS))
        self.assertTrue(
            all(e["evidence_state"] == "NOT_ESTABLISHED" and not e["action_authorized"] for e in graph["dependencies"])
        )

    def test_all_243_collector_state_combinations_stay_unqualified(self):
        for states in itertools.product(("VERIFIED", "UNKNOWN", "UNAVAILABLE"), repeat=5):
            with self.subTest(states=states):
                snapshot = estate(dict(zip(ALL, states)))
                fabric = project_ontology(snapshot, now=NOW)["release_fabric"]
                self.assertEqual(fabric["independently_qualified_stages"], 0)
                self.assertFalse(fabric["production_qualified"])
                self.assertFalse(fabric["can_deploy"])
                self.assertFalse(fabric["financial_revenue_verified"])
                by_id = {s["id"]: s for s in fabric["stages"]}
                cf, dns = states[2:4]
                expected = (
                    "VERIFIED"
                    if cf == dns == "VERIFIED"
                    else ("UNAVAILABLE" if cf == dns == "UNAVAILABLE" else "UNKNOWN")
                )
                self.assertEqual(by_id["cloudflare_edge"]["collector_state"], expected)

    def test_stale_successful_collector_is_not_promoted(self):
        snapshot = estate()
        snapshot["generated_at"] = "2026-11-15T21:00:00Z"
        result = project_ontology(snapshot, now=NOW)
        self.assertEqual(result["verified_sources"], 0)
        self.assertTrue(all(s["collector_state"] != "VERIFIED" for s in result["release_fabric"]["stages"]))
        self.assertEqual(result["release_fabric"]["independently_qualified_stages"], 0)

    def test_missing_source_and_external_canonical_links_never_leak_sensitive_data(self):
        snapshot = estate()
        snapshot["collectors"]["github"] = {}
        snapshot["collectors"]["huggingface"]["evidence_ref"] = " "
        snapshot["collectors"]["cloudflare"]["truth_state"] = ["VERIFIED"]
        result = project_ontology(snapshot, now=NOW)
        body = json.dumps(result)
        for forbidden in (
            "NEVER_EXPORT_THIS",
            "PRIVATE_FIXTURE_ID",
            "NOT_AN_ACTUAL_SIGNATURE",
            "opaque:synthetic-evidence",
        ):
            self.assertNotIn(forbidden, body)
        graph = result["release_fabric"]
        self.assertEqual(graph["collector_verified_stages"], 1)
        self.assertFalse(graph["production_qualified"])

    def test_foreign_graph_nodes_or_invalid_source_fingerprint_do_not_upgrade(self):
        nodes = [
            {"id": "source:github", "truth_state": "VERIFIED"},
            {"id": "source:secrets", "truth_state": "VERIFIED", "value": "PRIVATE"},
            {"id": "model:fake", "truth_state": "VERIFIED"},
        ]
        graph = release_fabric.project(nodes, "a" * 64)
        self.assertEqual(graph["collector_verified_stages"], 1)
        self.assertNotIn("PRIVATE", json.dumps(graph))
        with self.assertRaises(ValueError):
            release_fabric.project(nodes, "main")
        with self.assertRaises(ValueError):
            release_fabric.project(nodes, "A" * 64)

    def test_source_fingerprint_change_alters_graph_fingerprint_not_authority(self):
        one = release_fabric.project([], "a" * 64)
        two = release_fabric.project([], "b" * 64)
        self.assertNotEqual(one["content_sha256"], two["content_sha256"])
        self.assertEqual(one["independently_qualified_stages"], two["independently_qualified_stages"])
        self.assertFalse(one["fingerprint_is_signature"])
        self.assertFalse(two["fingerprint_is_signature"])


if __name__ == "__main__":
    unittest.main()

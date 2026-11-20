"""Two-sided, synthetic source-binding tests for the read-only release impact view.

The test oracle is independent of release_impact._validated. Its original-base
negative controls must FAIL with a stale basis, and pass after source binding.
No provider, agent, filesystem mutation, signing or runtime deployment.
"""
from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone

from backend import ontology, release_fabric, release_impact

NOW = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
STAMP = (NOW - timedelta(seconds=5)).isoformat()


def clean():
    collectors = {
        key: {
            "truth_state": "VERIFIED",
            "verified_at": STAMP,
            "evidence_ref": "test-observation:" + key,
        }
        for key in release_impact.SELECTABLE
    }
    return ontology.project(
        {"generated_at": STAMP, "collectors": collectors}, now=NOW
    )


def refingerprint(snapshot, *, change_basis=False):
    """Model a rehashing adversary; no cryptographic authentication assumed."""
    if change_basis:
        snapshot["source_snapshot_sha256"] = ontology.digest(
            {
                "source_generated_at": snapshot["source_generated_at"],
                "observations": [
                    (
                        node["id"],
                        node["truth_state"],
                        node.get("observed_at"),
                        node.get("evidence_ref_sha256"),
                    )
                    for node in snapshot["nodes"][1:]
                ],
            }
        )
    snapshot["release_fabric"] = release_fabric.project(
        snapshot["nodes"], snapshot["source_snapshot_sha256"]
    )
    snapshot["content_sha256"] = ontology.digest(
        {key: value for key, value in snapshot.items() if key != "content_sha256"}
    )
    return snapshot


def evaluate(snapshot, pinned=None):
    return release_impact.simulate(
        snapshot, "github", pinned or snapshot["source_snapshot_sha256"]
    )


class SnapshotBindingTests(unittest.TestCase):
    def test_unmodified_ontology_is_accepted_without_authority(self):
        original = clean()
        result = evaluate(original)
        self.assertEqual(result["source_observation_before"], "VERIFIED")
        self.assertFalse(result["action_authorized"])
        self.assertFalse(result["can_deploy"])
        self.assertFalse(result["production_qualified"])
        self.assertFalse(result["fingerprint_is_signature"])
        self.assertNotIn("source_authenticated", result)

    def test_rehashed_fabric_cannot_upgrade_collector_under_old_basis(self):
        original = clean()
        candidate = copy.deepcopy(original)
        candidate["nodes"][1]["truth_state"] = "UNAVAILABLE"
        refingerprint(candidate)
        self.assertEqual(
            candidate["source_snapshot_sha256"], original["source_snapshot_sha256"]
        )
        with self.assertRaisesRegex(ValueError, "SOURCE_SNAPSHOT_BASIS_MISMATCH"):
            evaluate(candidate, original["source_snapshot_sha256"])

    def test_timestamp_substitution_with_stale_basis_is_denied(self):
        candidate = clean()
        candidate["nodes"][2]["observed_at"] = "2026-11-19T21:58:00+00:00"
        refingerprint(candidate)
        with self.assertRaisesRegex(ValueError, "SOURCE_SNAPSHOT_BASIS_MISMATCH"):
            evaluate(candidate)

    def test_evidence_hash_substitution_with_stale_basis_is_denied(self):
        candidate = clean()
        candidate["nodes"][3]["evidence_ref_sha256"] = "f" * 64
        refingerprint(candidate)
        with self.assertRaisesRegex(ValueError, "SOURCE_SNAPSHOT_BASIS_MISMATCH"):
            evaluate(candidate)

    def test_source_timestamp_substitution_with_stale_basis_is_denied(self):
        candidate = clean()
        candidate["source_generated_at"] = "2026-11-19T21:57:00+00:00"
        refingerprint(candidate)
        with self.assertRaisesRegex(ValueError, "SOURCE_SNAPSHOT_BASIS_MISMATCH"):
            evaluate(candidate)

    def test_snapshot_node_cannot_claim_action_authority(self):
        candidate = clean()
        candidate["nodes"][0]["action_authorized"] = True
        refingerprint(candidate)
        with self.assertRaisesRegex(ValueError, "SNAPSHOT_NODE_INVALID"):
            evaluate(candidate)

    def test_collector_node_cannot_claim_action_authority(self):
        candidate = clean()
        candidate["nodes"][1]["action_authorized"] = True
        refingerprint(candidate)
        with self.assertRaisesRegex(ValueError, "SOURCE_NODE_INVALID"):
            evaluate(candidate)

    def test_collector_node_cannot_add_private_metadata(self):
        candidate = clean()
        candidate["nodes"][2]["private_prompt"] = "DO_NOT_EXPORT"
        refingerprint(candidate)
        with self.assertRaisesRegex(ValueError, "SOURCE_NODE_INVALID"):
            evaluate(candidate)

    def test_missing_observed_at_field_is_not_equivalent_to_none(self):
        candidate = clean()
        del candidate["nodes"][2]["observed_at"]
        refingerprint(candidate, change_basis=True)
        with self.assertRaisesRegex(ValueError, "SOURCE_NODE_INVALID"):
            evaluate(candidate)

    def test_malformed_evidence_digest_denied_even_when_rehashed(self):
        candidate = clean()
        candidate["nodes"][2]["evidence_ref_sha256"] = "not-a-digest"
        refingerprint(candidate, change_basis=True)
        with self.assertRaisesRegex(ValueError, "SOURCE_NODE_INVALID"):
            evaluate(candidate)

    def test_wrong_order_denied_even_when_rehashed(self):
        candidate = clean()
        candidate["nodes"][1], candidate["nodes"][2] = (
            candidate["nodes"][2], candidate["nodes"][1]
        )
        refingerprint(candidate, change_basis=True)
        with self.assertRaisesRegex(ValueError, "SOURCE_NODE_INVALID"):
            evaluate(candidate)

    def test_duplicate_source_id_is_denied(self):
        candidate = clean()
        candidate["nodes"][4]["id"] = "source:github"
        refingerprint(candidate, change_basis=True)
        with self.assertRaises(ValueError):
            evaluate(candidate)

    def test_omitted_source_node_is_denied(self):
        candidate = clean()
        candidate["nodes"].pop()
        with self.assertRaises(ValueError):
            evaluate(candidate)

    def test_generated_at_null_is_valid_when_emitted_by_ontology(self):
        absent = ontology.project(
            {"collectors": {}}, now=NOW
        )
        self.assertIsNone(absent["source_generated_at"])
        result = evaluate(absent)
        self.assertEqual(result["source_observation_before"], "UNAVAILABLE")
        self.assertFalse(result["observation_changed"])

    def test_null_observation_and_hash_allowed_from_emitted_schema(self):
        record = ontology.project(
            {"generated_at": STAMP, "collectors": {"github": {}}},
            now=NOW,
        )
        self.assertIsNone(record["nodes"][1]["observed_at"])
        self.assertIsNone(record["nodes"][1]["evidence_ref_sha256"])
        result = evaluate(record)
        self.assertEqual(result["source_observation_before"], "UNAVAILABLE")

    def test_overlong_generated_at_denied_even_if_rehashed(self):
        record = clean()
        record["source_generated_at"] = "x" * 80
        refingerprint(record, change_basis=True)
        with self.assertRaisesRegex(ValueError, "SOURCE_GENERATED_AT_INVALID"):
            evaluate(record)

    def test_malformed_node_reason_is_denied(self):
        record = clean()
        record["nodes"][3]["reason_code"] = "PRODUCTION_AUTHORIZED"
        refingerprint(record)
        with self.assertRaisesRegex(ValueError, "SOURCE_NODE_INVALID"):
            evaluate(record)

    def test_valid_rehashed_but_untrusted_basis_is_never_authority(self):
        """Structural self-consistency is weaker than origin authentication."""
        record = clean()
        record["nodes"][1]["truth_state"] = "UNAVAILABLE"
        refingerprint(record, change_basis=True)
        result = evaluate(record)
        self.assertFalse(result["action_authorized"])
        self.assertFalse(result["production_qualified"])
        self.assertFalse(result["fingerprint_is_signature"])
        self.assertEqual(result["source_observation_before"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()

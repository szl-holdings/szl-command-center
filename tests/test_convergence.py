"""Adversarial offline regression tests for the temporal convergence witness."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from backend import convergence as cv

A, B = "a" * 40, "b" * 40


def fixtures(revision=A, ready=False):
    storage = {
        "schema": "szl.a11oy-storage-status/v2", "mode": "FENCED",
        "role": "WRITER", "claim": "CLEAN", "writable": True,
        "epoch": 291, "alert": False, "pending_publish": [],
        "active_errors": {},
        "lease": {"state": "ACTIVE", "sequence": 22167, "heartbeat_age_s": 5.5},
        "stores": {
            name: {"health": "OK", "origin": "RESTORED",
                   "snapshot_failures": 0, "last_error_code": None}
            for name in cv.STORES
        },
    }
    build = {"status": "OBSERVED",
             "build": {"revision": revision,
                       "field_evidence": {"revision": "OBSERVED"}}}
    health = {"status": "ok", "operational_readiness": {
        "ready": ready, "status": "READY" if ready else "NOT_READY"}}
    h, p = cv.ORIGINS
    return {
        h + cv.ROUTES["build"]: build,
        h + cv.ROUTES["storage"]: storage,
        h + cv.ROUTES["health"]: health,
        p + cv.ROUTES["build"]: copy.deepcopy(build),
        p + cv.ROUTES["storage"]: copy.deepcopy(storage),
    }


def result(payload=None, heads=(A, A)):
    payload = payload or fixtures()
    iterator = iter(heads)
    return cv.collect(
        head_reader=lambda: next(iterator),
        fetcher=lambda url: json.dumps(payload[url]).encode("utf-8"),
        clock=lambda: "2026-11-17T05:00:00Z",
    )


class TestTemporalWitness(unittest.TestCase):
    def test_match_is_not_certificate(self):
        data = result()
        self.assertEqual(data["source"]["state"], "DECLARATIONS_MATCH")
        self.assertEqual(data["storage"]["state"], "HEALTHY_REPORTED")
        self.assertTrue(data["observational_convergence"])
        self.assertFalse(data["production_qualified"])
        self.assertFalse(data["can_deploy"])
        self.assertEqual(data["gate_vector"][-1]["proof"], "NOT_EVALUATED")
        self.assertIn("INDEPENDENT_EXECUTION_PROOF_NOT_VERIFIED",
                      data["blocker_codes"])
        self.assertEqual(len(data["evidence"]), 5)
        self.assertTrue(all("body_sha256" in row for row in data["evidence"]))
        self.assertNotIn('"stores"', json.dumps(data["evidence"]))
        unsigned = {k: v for k, v in data.items() if k != "observation_sha256"}
        sha = hashlib.sha256(json.dumps(unsigned, sort_keys=True,
                             separators=(",", ":"), allow_nan=False,
                             ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(data["observation_sha256"], sha)

    def test_head_changes_during_capture(self):
        data = result(heads=(A, B))
        self.assertEqual(data["source"]["state"], "MAIN_MOVED")
        self.assertFalse(data["observational_convergence"])
        self.assertIn("MAIN_CHANGED_DURING_CAPTURE", data["blocker_codes"])

    def test_source_drift_across_origins(self):
        payload = fixtures()
        payload[cv.ORIGINS[1] + cv.ROUTES["build"]]["build"]["revision"] = B
        data = result(payload)
        self.assertEqual(data["source"]["state"], "DRIFT")
        self.assertFalse(data["can_deploy"])

    def test_matching_old_runtime_is_not_current(self):
        data = result(fixtures(B))
        self.assertFalse(data["observational_convergence"])
        self.assertIn("SOURCE_DRIFT", data["blocker_codes"])

    def test_absent_seventh_store_blocks(self):
        payload = fixtures()
        del payload[cv.ORIGINS[0] + cv.ROUTES["storage"]]["stores"]["gdw"]
        data = result(payload)
        self.assertEqual(data["storage"]["state"], "UNQUALIFIED")
        self.assertIn("REQUIRED_STORE_SET_MISMATCH", data["blocker_codes"])

    def test_writer_epoch_and_sequence_must_agree(self):
        payload = fixtures()
        payload[cv.ORIGINS[1] + cv.ROUTES["storage"]]["epoch"] = 292
        data = result(payload)
        self.assertFalse(data["observational_convergence"])
        self.assertIn("STORAGE_ORIGINS_DISAGREE", data["blocker_codes"])

    def test_readiness_string_true_does_not_pass(self):
        payload = fixtures(ready=True)
        payload[cv.ORIGINS[0] + cv.ROUTES["health"]]["operational_readiness"]["ready"] = "true"
        data = result(payload)
        self.assertEqual(data["frontier"]["state"], "NOT_READY_OR_UNKNOWN")

    def test_even_native_ready_report_is_not_execution_attestation(self):
        data = result(fixtures(ready=True))
        self.assertEqual(data["frontier"]["state"], "READY_REPORTED")
        self.assertFalse(data["production_qualified"])

    def test_fail_closed_on_http_403(self):
        payload = fixtures()
        def fetch(url):
            if url == cv.ORIGINS[1] + cv.ROUTES["build"]:
                raise cv.HTTPError(url, 403, "challenge", {}, None)
            return json.dumps(payload[url]).encode()
        data = cv.collect(head_reader=lambda: A, fetcher=fetch,
                          clock=lambda: "2026-11-17T05:00:00Z")
        self.assertFalse(data["observational_convergence"])
        self.assertIn("HTTP_403_BUILD", data["blocker_codes"])

    def test_duplicate_json_keys_rejected(self):
        self.assertRaises(cv.InvalidObservation, cv._parse,
                          b'{"status":"OBSERVED","status":"OBSERVED"}')

    def test_nonfinite_heartbeat_rejected_with_honest_gap(self):
        payload = fixtures()
        for o in cv.ORIGINS:
            payload[o + cv.ROUTES["storage"]]["lease"]["heartbeat_age_s"] = float("inf")
        data = result(payload)
        self.assertFalse(data["observational_convergence"])
        self.assertIn("STATE_PRESERVATION_UNQUALIFIED", data["blocker_codes"])
        json.dumps(data, allow_nan=False)

    def test_missing_main_is_unknown_not_green(self):
        def head():
            raise RuntimeError("rate limited")
        payload = fixtures()
        data = cv.collect(head_reader=head,
                          fetcher=lambda u: json.dumps(payload[u]).encode(),
                          clock=lambda: "2026-11-17T05:00:00Z")
        self.assertEqual(data["source"]["state"], "UNKNOWN")
        self.assertFalse(data["observational_convergence"])

    def test_bounded_body(self):
        self.assertRaises(cv.InvalidObservation, cv._parse,
                          b"x" * (cv.MAX_RESPONSE + 1))

    def test_foreign_target_rejected_before_http(self):
        self.assertRaises(cv.InvalidObservation, cv._get,
                          "https://example.com/anything")

    def test_redirect_not_treated_as_success(self):
        with patch.object(cv, "build_opener") as mock:
            resp = mock.return_value.open.return_value.__enter__.return_value
            resp.status = 200
            resp.geturl.return_value = "https://example.com/other"
            self.assertRaises(cv.InvalidObservation, cv._get,
                              cv.ORIGINS[0] + cv.ROUTES["build"])


if __name__ == "__main__":
    unittest.main()

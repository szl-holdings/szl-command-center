"""Historical evidence cannot replace the current collector observation."""

import copy
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class EstateSnapshotTests(unittest.TestCase):
    def live(self, state="UNAVAILABLE"):
        return {
            "generated_at": "2026-11-02T00:00:00Z",
            "summary": {"estate_state": "UNKNOWN", "panels_verified": 1},
            "collectors": {
                "github": {"truth_state": state, "reason": "rate limited"},
                "dns": {"truth_state": "VERIFIED", "value": "current DNS evidence"},
                "cloudflare": {"truth_state": "UNAVAILABLE", "reason": "no credential"},
            },
        }

    def test_degraded_github_keeps_other_current_observations_and_failure_reason(self):
        snapshot = {
            "generated_at": "2026-08-01T00:00:00Z",
            "summary": {"estate_state": "VERIFIED", "panels_verified": 5},
            "collectors": {"github": {"truth_state": "VERIFIED"}},
            "_served_from": "baked-snapshot",
        }
        for state in ("UNAVAILABLE", "UNKNOWN"):
            with self.subTest(state=state):
                payload = self.live(state)
                original = copy.deepcopy(payload)
                with patch.object(main, "_cached", return_value=payload), patch.object(
                    main, "_snapshot", return_value=snapshot
                ):
                    result = json.loads(main.api_estate().body)
                self.assertEqual(result["collectors"], original["collectors"])
                self.assertEqual(result["summary"], original["summary"])
                self.assertEqual(result["generated_at"], original["generated_at"])
                self.assertEqual(result["_historical_snapshot"], snapshot)
                self.assertEqual(payload, original)
                self.assertNotIn("_served_from", result)

    def test_verified_github_does_not_attach_snapshot(self):
        payload = self.live("VERIFIED")
        with patch.object(main, "_cached", return_value=payload), patch.object(
            main, "_snapshot"
        ) as snapshot:
            result = json.loads(main.api_estate().body)
        self.assertEqual(result, payload)
        snapshot.assert_not_called()

    def test_missing_snapshot_keeps_current_failure(self):
        payload = self.live()
        with patch.object(main, "_cached", return_value=payload), patch.object(
            main, "_snapshot", return_value=None
        ):
            result = json.loads(main.api_estate().body)
        self.assertEqual(result, payload)

    def test_shipped_snapshot_is_supplemental_even_when_it_has_verified_states(self):
        payload = self.live()
        with patch.object(main, "_cached", return_value=payload):
            result = json.loads(main.api_estate().body)
        self.assertEqual(result["collectors"], payload["collectors"])
        self.assertEqual(result["summary"], payload["summary"])
        self.assertEqual(result["_historical_snapshot"]["_served_from"], "baked-snapshot")

    def test_http_routes_preserve_failures_with_shipped_snapshot_files(self):
        payloads = {
            "estate": self.live(),
            "verticals": {"verticals": [{"truth_state": "UNAVAILABLE", "reason": "timeout"}]},
        }
        with patch.object(main, "_cached", side_effect=lambda name, producer: payloads[name]):
            with TestClient(main.app) as client:
                for name, payload in payloads.items():
                    with self.subTest(route=name):
                        response = client.get("/api/" + name)
                        self.assertEqual(response.status_code, 200)
                        result = response.json()
                        self.assertEqual(result.pop("_historical_snapshot")["_served_from"], "baked-snapshot")
                        self.assertEqual(result, payload)


if __name__ == "__main__":
    unittest.main()

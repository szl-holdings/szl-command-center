"""Historical DNS evidence must stay unavailable and separate from live state."""

import copy
import json
import unittest
from unittest.mock import patch

from backend import main
from backend.collectors.base import roll_up


class DnsSnapshotTests(unittest.TestCase):
    def historical_snapshot(self):
        live = {
            "generated_at": "2026-11-02T00:00:00Z",
            "summary": {
                "panels_total": 2,
                "panels_verified": 0,
                "verified_ratio": 0.0,
                "estate_state": "UNKNOWN",
                "states": {"github": "UNAVAILABLE", "dns": "UNKNOWN"},
            },
            "collectors": {
                "github": {"truth_state": "UNAVAILABLE", "reason": "no credential"},
                "dns": {"truth_state": "UNKNOWN", "reason": "DNSSEC chain not validated"},
            },
        }
        original = copy.deepcopy(live)
        # Keep the actual route, loader and committed snapshot. Only suppress
        # the live producer so this test cannot make a provider request.
        with patch.object(main, "_cached", return_value=live):
            response = main.api_estate()
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.body)
        snapshot = result.pop("_historical_snapshot")
        self.assertEqual(snapshot["_served_from"], "baked-snapshot")
        self.assertNotIn("_served_from", result)
        self.assertEqual(result, original)
        self.assertEqual(live, original)
        return snapshot

    def test_baked_dns_diagnostics_are_unavailable(self):
        data = self.historical_snapshot()
        dns = data["collectors"]["dns"]
        self.assertEqual(dns["truth_state"], "UNAVAILABLE")
        for name, domain in dns["value"].items():
            with self.subTest(domain=name):
                self.assertEqual(domain["truth_state"], "UNAVAILABLE")
                self.assertIsNone(domain["value"])
                self.assertIn("no fresh query", domain["reason"])

    def test_historical_summary_does_not_count_dns_as_verified(self):
        data = self.historical_snapshot()
        states = {name: item["truth_state"] for name, item in data["collectors"].items()}
        summary = data["summary"]
        verified = sum(state == "VERIFIED" for state in states.values())
        self.assertEqual(summary["states"]["dns"], "UNAVAILABLE")
        self.assertEqual(summary["states"], states)
        self.assertEqual(summary["panels_total"], len(states))
        self.assertEqual(summary["panels_verified"], verified)
        self.assertEqual(summary["verified_ratio"], verified / len(states))
        self.assertEqual(summary["estate_state"], roll_up(list(states.values())))


if __name__ == "__main__":
    unittest.main()

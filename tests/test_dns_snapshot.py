"""The real baked fallback must not restore rejected DNS observations."""

import json
import unittest
from unittest.mock import patch

from backend import main
from backend.collectors.base import roll_up


class DnsSnapshotTests(unittest.TestCase):
    def fallback(self):
        live = {"collectors": {"github": {"truth_state": "UNAVAILABLE"}}}
        # Keep the actual route, loader and committed snapshot. Only suppress
        # the live producer so this test cannot make a provider request.
        with patch.object(main, "_cached", return_value=live):
            response = main.api_estate()
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.body)
        self.assertEqual(result["_served_from"], "baked-snapshot")
        return result

    def test_baked_dns_diagnostics_are_unavailable(self):
        data = self.fallback()
        dns = data["collectors"]["dns"]
        self.assertEqual(dns["truth_state"], "UNAVAILABLE")
        for name, domain in dns["value"].items():
            with self.subTest(domain=name):
                self.assertEqual(domain["truth_state"], "UNAVAILABLE")
                self.assertIsNone(domain["value"])
                self.assertIn("no fresh query", domain["reason"])

    def test_fallback_summary_does_not_count_dns_as_verified(self):
        data = self.fallback()
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

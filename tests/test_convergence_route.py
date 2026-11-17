"""FastAPI route integration for the independent convergence witness."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class ConvergenceRouteTest(unittest.TestCase):
    def test_route_returns_read_only_convergence_and_static_client(self):
        fixture = {
            "schema": "szl.temporal-convergence-observation/v1",
            "scope": "UNSIGNED_READ_ONLY_OBSERVATION",
            "production_qualified": False,
            "can_deploy": False,
            "observational_convergence": False,
            "main": {"before": None, "after": None},
            "source": {"state": "UNKNOWN", "declared_revisions": {}},
            "storage": {"state": "UNQUALIFIED", "origins": []},
            "frontier": {"state": "NOT_READY_OR_UNKNOWN", "native_state": "UNKNOWN"},
            "gate_vector": [
                {"gate": "SOURCE_DECLARATIONS", "observed": False},
                {"gate": "STATE_PRESERVATION", "observed": False},
                {"gate": "FRONTIER_READINESS", "observed": False},
                {"gate": "EXECUTION_AUTHORITY", "observed": False},
            ],
            "blocker_codes": ["GITHUB_MAIN_BEFORE_UNAVAILABLE"],
            "evidence": [],
            "observation_sha256": "a" * 64,
        }
        with patch.object(main.convergence, "collect", return_value=fixture), \
             patch.object(main, "_response_cache", main.ResponseCache(60)):
            client = TestClient(main.app)
            response = client.get("/api/convergence")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), fixture)
            static = client.get("/convergence.js")
            self.assertEqual(static.status_code, 200)
            self.assertIn("UNSIGNED_READ_ONLY_OBSERVATION", static.text)
            page = client.get("/")
            self.assertIn('id="convergence"', page.text)
            self.assertIn('src="/convergence.js"', page.text)


if __name__ == "__main__":
    unittest.main()

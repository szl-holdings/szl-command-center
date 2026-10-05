"""Offline checks for the verticals route's documented snapshot fallback."""

import json
import unittest
from unittest.mock import patch

from backend import main


class VerticalsSnapshotTests(unittest.TestCase):
    def response_for(self, states, snapshot=None):
        payload = {"verticals": [{"truth_state": state} for state in states], "source": "live"}
        with patch.object(main, "_cached", return_value=payload), patch.object(
            main, "_snapshot", return_value=snapshot
        ):
            response = main.api_verticals()
        return json.loads(response.body), payload

    def test_all_unavailable_uses_the_declared_snapshot(self):
        snapshot = {"verticals": [], "_served_from": "baked-snapshot", "observed_at": "fixture"}
        response, _ = self.response_for(["UNAVAILABLE", "UNAVAILABLE"], snapshot)
        self.assertEqual(response, snapshot)

    def test_all_unknown_uses_the_declared_snapshot(self):
        snapshot = {"verticals": [], "_served_from": "baked-snapshot"}
        response, _ = self.response_for(["UNKNOWN"], snapshot)
        self.assertEqual(response, snapshot)

    def test_mixed_unknown_and_unavailable_uses_the_declared_snapshot(self):
        snapshot = {"verticals": [], "_served_from": "baked-snapshot"}
        response, _ = self.response_for(["UNKNOWN", "UNAVAILABLE"], snapshot)
        self.assertEqual(response, snapshot)

    def test_a_verified_vertical_keeps_the_live_observation(self):
        response, payload = self.response_for(
            ["UNAVAILABLE", "VERIFIED"], {"verticals": [], "_served_from": "baked-snapshot"}
        )
        self.assertEqual(response, payload)

    def test_missing_snapshot_keeps_the_unavailable_live_result(self):
        response, payload = self.response_for(["UNAVAILABLE"])
        self.assertEqual(response, payload)

    def test_empty_verticals_keeps_the_live_result(self):
        response, payload = self.response_for(
            [], {"verticals": [], "_served_from": "baked-snapshot"}
        )
        self.assertEqual(response, payload)

    def test_malformed_verticals_cannot_activate_snapshot_fallback(self):
        for verticals in ({"entry": {"truth_state": "UNAVAILABLE"}}, [None], ["UNAVAILABLE"]):
            with self.subTest(verticals=verticals):
                payload = {"verticals": verticals, "source": "live"}
                with patch.object(main, "_cached", return_value=payload), patch.object(
                    main, "_snapshot", return_value={"_served_from": "baked-snapshot"}
                ):
                    response = main.api_verticals()
                self.assertEqual(json.loads(response.body), payload)


if __name__ == "__main__":
    unittest.main()

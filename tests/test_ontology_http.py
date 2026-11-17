"""Transport and frontend contract: no live collectors or external calls."""
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import main

CURRENT = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fixture():
    return {"generated_at": CURRENT, "collectors": {
        name: {"truth_state": "VERIFIED", "verified_at": CURRENT,
               "evidence_ref": "opaque:fixture-" + name,
               "value": {"secret": "DO_NOT_LEAK"}}
        for name in ("github", "huggingface", "cloudflare", "dns", "receipts")
    }}


class OntologyHttpTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)

    def test_default_denies_and_does_not_collect(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(main, "_cached") as collector:
            response = self.client.get("/api/ontology")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["reason_code"], "FEATURE_NOT_ADMITTED")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        collector.assert_not_called()

    def test_enabled_transport_is_readonly_and_bound(self):
        data = fixture()
        with patch.dict(os.environ, {"SZL_ONTOLOGY_READONLY_ENABLED": "1"}), patch.object(main, "_cached", return_value=data) as collector:
            response = self.client.get("/api/ontology")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source_generated_at"], CURRENT)
        self.assertEqual(response.json()["rollup"], "VERIFIED")
        self.assertEqual(response.json()["authorization"]["can_execute_actions"], False)
        self.assertNotIn("DO_NOT_LEAK", response.text)
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(collector.call_args.args[0], "estate")

    def test_frontend_contains_ontology_widget_and_javascript(self):
        html = self.client.get("/")
        js = self.client.get("/app.js")
        css = self.client.get("/styles.css")
        self.assertEqual((html.status_code, js.status_code, css.status_code), (200, 200, 200))
        self.assertIn('id="ontology-graph"', html.text)
        self.assertIn("SOURCE_SNAPSHOT_MISMATCH", js.text)
        self.assertIn("ontology-sources", css.text)
        self.assertNotIn("innerHTML =", js.text[js.text.index("function renderOntology(payload)"):js.text.index("function refresh()")])


if __name__ == "__main__":
    unittest.main()

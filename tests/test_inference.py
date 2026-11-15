from __future__ import annotations

from backend import inference


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_snapshot_reports_verified_contract(monkeypatch):
    def fake_request(method, url, **kwargs):
        if method == "GET" and url.endswith("/health"):
            return FakeResponse(200, {"status": "ok"})
        if method == "GET" and url.endswith("/v1/models"):
            return FakeResponse(200, {"models": [{"id": inference.EXPECTED_MODEL}]})
        return FakeResponse(
            402,
            {
                "x402Version": 2,
                "accepts": [{"network": "eip155:8453", "amount": "20000"}],
            },
        )

    monkeypatch.setattr(inference.requests, "request", fake_request)
    data = inference.snapshot()

    assert data["truth_state"] == "VERIFIED"
    assert all(item["truth_state"] == "VERIFIED" for item in data["checks"])
    assert data["checks"][2]["evidence"]["payment_signature_sent"] is False


def test_showcase_is_bounded_and_contains_links(monkeypatch):
    monkeypatch.setattr(
        inference,
        "snapshot",
        lambda: {
            "endpoint": "https://inference.a-11-oy.com",
            "model": inference.EXPECTED_MODEL,
            "observed_at": "2026-11-15T15:02:00Z",
            "truth_state": "VERIFIED",
            "checks": [
                {
                    "check": "health",
                    "truth_state": "VERIFIED",
                    "status_code": 200,
                    "detail": "public health response",
                    "evidence": {"body_status": "ok"},
                },
                {
                    "check": "models",
                    "truth_state": "VERIFIED",
                    "status_code": 200,
                    "detail": "expected model is exposed",
                    "evidence": {"models": [inference.EXPECTED_MODEL]},
                },
                {
                    "check": "payment_gate",
                    "truth_state": "VERIFIED",
                    "status_code": 402,
                    "detail": "unsigned completion was rejected by x402 v2",
                    "evidence": {"network": "eip155:8453", "amount_atomic": "20000"},
                },
            ],
            "limits": ["No paid completion."],
        },
    )
    html = inference.render_showcase(inference.snapshot())
    assert "Measured Inference" in html
    assert "inference.a-11-oy.com" in html
    assert "paid completion" in html.lower()

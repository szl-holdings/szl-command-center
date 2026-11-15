from __future__ import annotations

import re

import pytest
import requests

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
    links = re.findall(r'href="([^"]+)"', html)
    assert links[:3] == [
        "https://inference.a-11-oy.com/",
        "https://inference.a-11-oy.com/v1/models",
        "https://a11oy.net/",
    ]
    assert "paid completion" in html.lower()


def test_inference_url_is_allow_listed():
    assert inference._validated_base_url("https://inference.a-11-oy.com") == "https://inference.a-11-oy.com"
    assert inference._validated_base_url("http://localhost:9000/") == "http://localhost:9000"
    assert inference._validated_base_url("https://127.0.0.1:8443") == "https://127.0.0.1:8443"

    for candidate in (
        "https://evil.example",
        "http://inference.a-11-oy.com",
        "https://inference.a-11-oy.com:443",
        "https://inference.a-11-oy.com/path",
        "https://user:password@inference.a-11-oy.com",
        "file:///etc/passwd",
    ):
        with pytest.raises(ValueError):
            inference._validated_base_url(candidate)


def test_probe_models_accepts_openai_data_shape(monkeypatch):
    def fake_request(method, url, **kwargs):
        return FakeResponse(200, {"data": [{"id": inference.EXPECTED_MODEL}]})

    monkeypatch.setattr(inference.requests, "request", fake_request)
    result = inference.probe_models()

    assert result["truth_state"] == "VERIFIED"
    assert result["evidence"]["models"] == [inference.EXPECTED_MODEL]


def test_snapshot_uses_short_response_cache(monkeypatch):
    calls = {"count": 0}

    def fake_request(method, url, **kwargs):
        calls["count"] += 1
        if method == "GET" and url.endswith("/health"):
            return FakeResponse(200, {"status": "ok"})
        if method == "GET" and url.endswith("/v1/models"):
            return FakeResponse(200, {"data": [{"id": inference.EXPECTED_MODEL}]})
        return FakeResponse(
            402,
            {"x402Version": 2, "accepts": [{"network": "eip155:8453", "amount": "20000"}]},
        )

    monkeypatch.setattr(inference.requests, "request", fake_request)
    monkeypatch.setattr(
        inference,
        "_snapshot_cache",
        inference.ResponseCache(inference.SNAPSHOT_CACHE_TTL_SECONDS),
    )

    first = inference.snapshot()
    second = inference.snapshot()

    assert first == second
    assert calls["count"] == 3
    assert inference.SNAPSHOT_CACHE_TTL_SECONDS == 30


def test_upstream_exception_text_is_not_returned(monkeypatch):
    secret = "upstream-secret-body"

    def fake_request(method, url, **kwargs):
        raise requests.RequestException(secret)

    monkeypatch.setattr(inference.requests, "request", fake_request)
    result = inference.probe_health()

    assert result["truth_state"] == "UNAVAILABLE"
    assert result["detail"] == "request failed: RequestException"
    assert secret not in str(result)



def test_malformed_upstream_body_is_not_echoed(monkeypatch):
    secret = "raw-upstream-body"

    def fake_request(method, url, **kwargs):
        return FakeResponse(
            402,
            {
                "x402Version": {"secret": secret},
                "accepts": secret,
                "unexpected": secret,
            },
        )

    monkeypatch.setattr(inference.requests, "request", fake_request)
    result = inference.probe_payment_gate()

    assert result["truth_state"] == "UNKNOWN"
    assert result["evidence"] == {
        "x402_version": None,
        "network": None,
        "amount_atomic": None,
        "payment_signature_sent": False,
    }
    assert secret not in str(result)

"""Measured public inference surface for the SZL Command Center.

This module intentionally probes only public, non-paying endpoints.  It exposes
the live Salad gateway as evidence with explicit truth states and a bounded
server-rendered card.  A payment signature is never generated or accepted here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import os
from typing import Any
from urllib.parse import urlparse

import requests
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .cache import ResponseCache

router = APIRouter()
DEFAULT_INFERENCE_URL = "https://inference.a-11-oy.com"
_ALLOWED_PUBLIC_HOST = "inference.a-11-oy.com"
_ALLOWED_LOCAL_HOSTS = {"localhost", "127.0.0.1"}
SNAPSHOT_CACHE_TTL_SECONDS = 30


def _validated_base_url(raw: str | None = None) -> str:
    """Return an allow-listed origin suitable for server-side probing.

    The public gateway is HTTPS-only. Local development may use HTTP(S) on
    localhost or 127.0.0.1, including a non-default port. Paths, credentials,
    query strings, fragments, redirects, and every other host are rejected so
    an environment variable cannot turn these collectors into an SSRF proxy.
    """
    value = (raw or DEFAULT_INFERENCE_URL).strip()
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise ValueError("SZL_INFERENCE_URL must be a valid allow-listed origin") from exc
    if not parsed.scheme or not host or parsed.username or parsed.password:
        raise ValueError("SZL_INFERENCE_URL must be a valid allow-listed origin")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("SZL_INFERENCE_URL must contain only an allow-listed origin")
    scheme = parsed.scheme.lower()
    if host == _ALLOWED_PUBLIC_HOST:
        if scheme != "https" or port is not None:
            raise ValueError("public SZL_INFERENCE_URL must use the canonical HTTPS origin")
    elif host in _ALLOWED_LOCAL_HOSTS:
        if scheme not in {"http", "https"}:
            raise ValueError("local SZL_INFERENCE_URL must use HTTP or HTTPS")
    else:
        raise ValueError("SZL_INFERENCE_URL host is not allow-listed")
    suffix = f":{port}" if port is not None else ""
    return f"{scheme}://{host}{suffix}"


INFERENCE_URL = _validated_base_url(os.getenv("SZL_INFERENCE_URL"))
TIMEOUT_SECONDS = float(os.getenv("SZL_INFERENCE_TIMEOUT_SECONDS", "4"))
_snapshot_cache = ResponseCache(SNAPSHOT_CACHE_TTL_SECONDS)
EXPECTED_MODEL = "ternary-bonsai-2-27b-pq2_0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _result(
    check: str,
    truth_state: str,
    *,
    status_code: int | None = None,
    detail: str = "",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "check": check,
        "truth_state": truth_state,
        "status_code": status_code,
        "detail": detail,
        "evidence": evidence or {},
        "observed_at": _now(),
        "source": INFERENCE_URL,
    }


def _json_response(method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
    response = requests.request(
        method,
        f"{INFERENCE_URL}{path}",
        timeout=TIMEOUT_SECONDS,
        allow_redirects=False,
        **kwargs,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return response.status_code, payload


def probe_health() -> dict[str, Any]:
    try:
        status, payload = _json_response("GET", "/health")
    except requests.RequestException as exc:
        return _result("health", "UNAVAILABLE", detail=f"request failed: {exc.__class__.__name__}")
    body_status = payload.get("status") if isinstance(payload, dict) else None
    if not isinstance(body_status, str):
        body_status = None
    ok = status == 200 and body_status == "ok"
    return _result(
        "health",
        "VERIFIED" if ok else "UNKNOWN",
        status_code=status,
        detail="public health response" if ok else "response did not match the declared health contract",
        evidence={"body_status": body_status},
    )


def probe_models() -> dict[str, Any]:
    try:
        status, payload = _json_response("GET", "/v1/models")
    except requests.RequestException as exc:
        return _result("models", "UNAVAILABLE", detail=f"request failed: {exc.__class__.__name__}")
    raw_models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        raw_models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        raw_models = []
    names = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        candidate = item.get("id") or item.get("name")
        if isinstance(candidate, str) and candidate:
            names.append(candidate[:128])
    matched = EXPECTED_MODEL in names
    return _result(
        "models",
        "VERIFIED" if status == 200 and matched else "UNKNOWN",
        status_code=status,
        detail="expected model is exposed" if matched else "expected model was not exposed",
        evidence={"models": names[:20], "expected_model": EXPECTED_MODEL},
    )


def probe_payment_gate() -> dict[str, Any]:
    request_body = {
        "model": EXPECTED_MODEL,
        "messages": [{"role": "user", "content": "public healthcheck"}],
        "max_tokens": 1,
    }
    try:
        status, payload = _json_response(
            "POST",
            "/v1/chat/completions",
            json=request_body,
            headers={"content-type": "application/json"},
        )
    except requests.RequestException as exc:
        return _result("payment_gate", "UNAVAILABLE", detail=f"request failed: {exc.__class__.__name__}")
    payload_dict = payload if isinstance(payload, dict) else {}
    accepts = payload_dict.get("accepts", [])
    if not isinstance(accepts, list):
        accepts = []
    first = accepts[0] if accepts and isinstance(accepts[0], dict) else {}
    amount = first.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (str, int, float)):
        amount = None
    elif len(str(amount)) > 64:
        amount = None
    network = first.get("network")
    if not isinstance(network, str) or len(network) > 128:
        network = None
    x402_version = payload_dict.get("x402Version")
    if not isinstance(x402_version, int) or isinstance(x402_version, bool):
        x402_version = None
    verified = status == 402 and x402_version == 2 and amount is not None and network is not None
    return _result(
        "payment_gate",
        "VERIFIED" if verified else "UNKNOWN",
        status_code=status,
        detail="unsigned completion was rejected by x402 v2" if verified else "payment posture did not match the expected contract",
        evidence={
            "x402_version": x402_version,
            "network": network,
            "amount_atomic": amount,
            "payment_signature_sent": False,
        },
    )


def _snapshot_uncached() -> dict[str, Any]:
    checks = [probe_health(), probe_models(), probe_payment_gate()]
    verified = sum(item["truth_state"] == "VERIFIED" for item in checks)
    return {
        "service": "SZL public inference gateway",
        "endpoint": INFERENCE_URL,
        "model": EXPECTED_MODEL,
        "observed_at": _now(),
        "truth_state": "VERIFIED" if verified == len(checks) else "UNKNOWN",
        "checks": checks,
        "limits": [
            "Reachability and payment-gate posture do not establish model quality.",
            "No paid completion or payment receipt is requested by this collector.",
            "A transport HTTP 200 is not a production-readiness certificate.",
        ],
    }


def snapshot() -> dict[str, Any]:
    return _snapshot_cache.get("inference-snapshot", _snapshot_uncached)


def _badge(item: dict[str, Any]) -> str:
    state = escape(str(item["truth_state"]))
    return f'<span class="badge badge-{state.lower()}">{state}</span>'


def render_showcase(data: dict[str, Any]) -> str:
    cards = []
    for item in data["checks"]:
        evidence = item.get("evidence", {})
        if item["check"] == "models":
            detail = escape(", ".join(evidence.get("models", [])) or item["detail"])
        elif item["check"] == "payment_gate":
            detail = escape(
                f'{evidence.get("network") or "network unavailable"} · '
                f'{evidence.get("amount_atomic") or "amount unavailable"} atomic units'
            )
        else:
            detail = escape(item["detail"])
        cards.append(
            f'<article class="check"><div class="label">{escape(item["check"])}</div>'
            f'<div class="status">{_badge(item)}</div>'
            f'<div class="detail">{detail}</div>'
            f'<div class="code">HTTP {escape(str(item.get("status_code") or "—"))}</div></article>'
        )
    observed = escape(str(data["observed_at"]))
    endpoint = escape(data["endpoint"], quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SZL · Measured Inference</title>
<meta name="description" content="Evidence-bounded public inference status for SZL Holdings.">
<style>
:root{{color-scheme:dark;--bg:#07101d;--panel:#0e1a2a;--line:#23344b;--text:#f3f7fc;--muted:#aebbd0;--accent:#c8d8ee}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(80% 60% at 50% -10%,#1b304c,#07101d 70%);color:var(--text);font:16px/1.55 system-ui,sans-serif}}
main{{max-width:1120px;margin:auto;padding:72px 24px 100px}}a{{color:var(--accent)}}.eyebrow,.code,.label{{font:12px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase}}
.eyebrow{{color:var(--accent)}}h1{{font-size:clamp(38px,6vw,72px);line-height:1.02;letter-spacing:-.04em;max-width:850px;margin:18px 0}}.lede{{color:var(--muted);max-width:760px;font-size:19px}}
.meta{{color:#8293aa;font:12px ui-monospace,monospace;margin-top:18px}}.actions{{display:flex;gap:12px;flex-wrap:wrap;margin:30px 0 54px}}
.btn{{border:1px solid var(--line);border-radius:10px;padding:12px 17px;text-decoration:none;font-weight:650}}.btn.primary{{background:var(--text);color:#07101d;border-color:var(--text)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}}.check{{background:#0e1a2add;border:1px solid var(--line);border-radius:14px;padding:21px;min-height:145px}}
.label{{color:#8293aa}}.status{{margin:12px 0 8px}.badge{{display:inline-flex;border:1px solid var(--line);border-radius:999px;padding:3px 9px;font:12px ui-monospace,monospace;letter-spacing:.08em}}.badge-verified{{color:var(--text);border-color:#b7c8dc}}.badge-unknown,.badge-unavailable{{color:var(--muted)}}
.detail{{color:var(--muted);min-height:44px}}.code{{color:#8293aa;margin-top:10px}}section{{margin-top:62px}}h2{{font-size:28px;letter-spacing:-.02em}}.limits{{border-left:3px solid var(--accent);background:var(--panel);padding:15px 20px;color:var(--muted)}}footer{{border-top:1px solid var(--line);margin-top:72px;padding-top:22px;color:#8293aa;font-size:13px}}
</style></head><body><main>
<div class="eyebrow">SZL / MEASURED INFERENCE</div>
<h1>Public inference with a visible evidence boundary.</h1>
<p class="lede">The Command Center probes the live Salad gateway for transport health, exposed model identity, and x402 payment posture. It never sends a payment signature and never turns reachability into a quality claim.</p>
<div class="actions"><a class="btn primary" href="{endpoint}/" target="_blank" rel="noopener">Open live UI ↗</a><a class="btn" href="{endpoint}/v1/models" target="_blank" rel="noopener">Inspect model registry ↗</a><a class="btn" href="https://a11oy.net/" target="_blank" rel="noopener">Open proof registry ↗</a></div>
<p class="meta">Observation: {observed} · Endpoint: {endpoint}</p>
<section><div class="grid">{''.join(cards)}</div></section>
<section><h2>Served contract</h2><div class="limits"><ul><li>Model: <code>{escape(EXPECTED_MODEL)}</code></li><li>Unpaid completion probes must receive x402 v2 before generation.</li><li>Paid completion, quality, latency, and uptime remain outside this observation.</li></ul></div></section>
<footer>SZL Holdings · <a href="https://github.com/szl-holdings/szl-router">router control plane</a> · <a href="https://huggingface.co/SZLHOLDINGS">Hugging Face</a> · <a href="https://a-11-oy.com/">Product</a></footer>
</main></body></html>"""


@router.get("/api/inference/snapshot")
def api_inference_snapshot() -> dict[str, Any]:
    return snapshot()


@router.get("/inference", response_class=HTMLResponse, include_in_schema=False)
def inference_showcase() -> HTMLResponse:
    return HTMLResponse(render_showcase(snapshot()))

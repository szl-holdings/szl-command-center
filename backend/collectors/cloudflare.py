"""Cloudflare collector — HTTPS against api.cloudflare.com.

Auth comes from the environment at runtime (CLOUDFLARE_API_TOKEN-style
variables). NEVER hardcode a token. If no token is present, the panel
returns UNAVAILABLE with that exact reason (CANON Law 1).

Per zone: DNSSEC status, total DNS record count, and how many of those
records are proxied through Cloudflare.
"""
from __future__ import annotations

import os

import requests

from .base import clip, envelope, roll_up, unavailable, verified

API = "https://api.cloudflare.com/client/v4"
TIMEOUT = 15
ZONES = ("a-11-oy.com", "a11oy.net")
TOKEN_ENV_VARS = ("CLOUDFLARE_API_TOKEN", "CF_API_TOKEN", "CLOUDFLARE_TOKEN")


def _token() -> str | None:
    for name in TOKEN_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _get(path: str, token: str, params: dict | None = None) -> dict:
    resp = requests.get(
        f"{API}{path}",
        params=params or {},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("success"):
        errors = body.get("errors") or []
        raise RuntimeError(clip("; ".join(str(e.get("message")) for e in errors) or "API error"))
    return body


def _zone(zone_name: str, token: str) -> dict:
    ref = f"{API}/zones?name={zone_name} (+/dnssec, /dns_records)"
    try:
        zones = _get("/zones", token, {"name": zone_name}).get("result") or []
        if not zones:
            return unavailable(ref, f"zone {zone_name} not visible to this token")
        zone_id = zones[0]["id"]
        dnssec = _get(f"/zones/{zone_id}/dnssec", token).get("result") or {}
        records = _get(
            f"/zones/{zone_id}/dns_records", token, {"per_page": 500}
        )
        result = records.get("result") or []
        info = records.get("result_info") or {}
        proxied = sum(1 for r in result if r.get("proxied"))
        return verified(
            {
                "zone": zone_name,
                "zone_id": zone_id,
                "dnssec_status": dnssec.get("status", "unknown"),
                "record_count": info.get("total_count", len(result)),
                "proxied_count": proxied,
            },
            ref,
        )
    except Exception as exc:  # noqa: BLE001
        return unavailable(ref, clip(exc))


def collect() -> dict:
    token = _token()
    if not token:
        return unavailable(
            f"{API}/zones",
            "no Cloudflare token in environment; set one of "
            + ", ".join(TOKEN_ENV_VARS)
            + " — UNAVAILABLE per Zero-Bandaid Law, never a guess",
        )
    zones = {name: _zone(name, token) for name in ZONES}
    state = roll_up([z["truth_state"] for z in zones.values()])
    env = envelope(zones, state, f"{API} (zones, dnssec, dns_records)")
    if state != "VERIFIED":
        reasons = [
            z.get("reason") for z in zones.values() if z["truth_state"] != "VERIFIED"
        ]
        env["reason"] = "; ".join(r for r in reasons if r)[:200]
    return env

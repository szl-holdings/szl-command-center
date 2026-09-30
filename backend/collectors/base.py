"""Truth-state envelope — the Command Center's core contract (CANON Law 1).

Nothing renders without a state. Every collector returns:

    {
        "value": <any JSON-serializable payload or None>,
        "truth_state": "VERIFIED" | "UNKNOWN" | "UNAVAILABLE",
        "verified_at": <RFC 3339 UTC timestamp of the observation>,
        "evidence_ref": <how this value was observed — command, URL, or path>,
        "reason": <only present when not VERIFIED — why>,
    }

VERIFIED   — observed directly, just now, from the named evidence source.
UNKNOWN    — observed, but the observation cannot support the claim
             (e.g. partial data, empty where data is expected).
UNAVAILABLE — the evidence source itself could not be reached
             (missing tool, missing token, timeout). An audited state,
             never a blank.
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

VERIFIED = "VERIFIED"
UNKNOWN = "UNKNOWN"
UNAVAILABLE = "UNAVAILABLE"


def utc_now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def envelope(
    value: Any,
    truth_state: str,
    evidence_ref: str,
    reason: Optional[str] = None,
) -> dict:
    env = {
        "value": value,
        "truth_state": truth_state,
        "verified_at": utc_now(),
        "evidence_ref": evidence_ref,
    }
    if reason:
        env["reason"] = reason
    return env


def verified(value: Any, evidence_ref: str) -> dict:
    return envelope(value, VERIFIED, evidence_ref)


def unknown(value: Any, evidence_ref: str, reason: str) -> dict:
    return envelope(value, UNKNOWN, evidence_ref, reason=reason)


def unavailable(evidence_ref: str, reason: str) -> dict:
    return envelope(None, UNAVAILABLE, evidence_ref, reason=reason)


def roll_up(states: list) -> str:
    """Aggregate sub-envelope truth states into one honest parent state.

    All VERIFIED -> VERIFIED. All UNAVAILABLE -> UNAVAILABLE.
    Anything mixed is UNKNOWN: partial evidence never upgrades to VERIFIED.
    """
    if not states:
        return UNAVAILABLE
    unique = set(states)
    if unique == {VERIFIED}:
        return VERIFIED
    if unique == {UNAVAILABLE}:
        return UNAVAILABLE
    if VERIFIED in unique and UNAVAILABLE not in unique and UNKNOWN not in unique:
        return VERIFIED
    return UNKNOWN


def reason_of(env: dict) -> str:
    return env.get("reason") or "no reason recorded"


def clip(text: str, limit: int = 180) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"

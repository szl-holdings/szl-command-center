"""Read-only proof graph projection of Command Center's existing estate snapshot.
No collector execution, graph inference, permissions or actions are added here.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone

from .collectors.base import roll_up

SCHEMA = "szl.readonly.evidence_graph.v1"
ORDER = ("github", "huggingface", "cloudflare", "dns", "receipts")
STATES = frozenset({"VERIFIED", "UNKNOWN", "UNAVAILABLE"})


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _fresh(iso, now, max_age_seconds=120):
    if not isinstance(iso, str):
        return False
    try:
        date = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    if date.tzinfo is None:
        return False
    age = (now - date.astimezone(timezone.utc)).total_seconds()
    return 0 <= age <= max_age_seconds


def project(estate, *, now=None):
    """Project only observed collector envelopes; no speculative graph edges.

    VERIFIED is downgraded if freshness or evidence identity is absent.
    Hashes are checksums, NOT signatures, proof of origin, or authorization.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    snapshot = estate if isinstance(estate, dict) else {}
    collectors = snapshot.get("collectors")
    collectors = collectors if isinstance(collectors, dict) else {}
    stamp = snapshot.get("generated_at")
    stamp = stamp if isinstance(stamp, str) and len(stamp) <= 40 else None
    snapshot_fresh = _fresh(stamp, now)
    nodes = []
    links = []
    for key in ORDER:
        env = collectors.get(key)
        env = env if isinstance(env, dict) else {}
        state = env.get("truth_state")
        if type(state) is not str or state not in STATES:
            state = "UNAVAILABLE"
        ref = env.get("evidence_ref")
        observed = env.get("verified_at")
        ref_valid = isinstance(ref, str) and bool(ref.strip()) and len(ref) <= 2048
        fresh = _fresh(observed, now)
        reason = "DIRECT_OBSERVATION"
        if not env:
            state, reason = "UNAVAILABLE", "COLLECTOR_MISSING"
        elif state == "VERIFIED" and not snapshot_fresh:
            state, reason = "UNKNOWN", "SNAPSHOT_STALE_OR_INVALID"
        elif state == "VERIFIED" and not ref_valid:
            state, reason = "UNKNOWN", "EVIDENCE_IDENTITY_MISSING"
        elif state == "VERIFIED" and not fresh:
            state, reason = "UNKNOWN", "OBSERVATION_STALE_OR_INVALID"
        elif state != "VERIFIED":
            reason = "UPSTREAM_NOT_VERIFIED"
        node = {
            "id": "source:" + key,
            "kind": "evidence_source",
            "label": key,
            "truth_state": state,
            "reason_code": reason,
            "observed_at": observed if isinstance(observed, str) and len(observed) <= 40 else None,
            "evidence_ref_sha256": hashlib.sha256(ref.encode("utf-8")).hexdigest() if ref_valid else None,
            "claim_scope": "collector_observation_only",
            "action_authorized": False,
        }
        nodes.append(node)
        # Links mean only "observed as a collector of this snapshot".
        links.append({"source": node["id"], "target": "snapshot:estate", "kind": "observed_in"})
    states = [n["truth_state"] for n in nodes]
    body = {
        "schema": SCHEMA,
        "scope": "read_only_collector_projection",
        "generated_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_generated_at": stamp,
        "source_snapshot_sha256": digest({
            "source_generated_at": stamp,
            "observations": [
                (n["id"], n["truth_state"], n["observed_at"], n["evidence_ref_sha256"])
                for n in nodes
            ],
        }),
        "nodes": [{"id": "snapshot:estate", "kind": "snapshot", "claim_scope": "projection_only", "action_authorized": False}, *nodes],
        "links": links,
        "rollup": roll_up(states),
        "verified_sources": sum(s == "VERIFIED" for s in states),
        "total_sources": len(states),
        "provenance": {
            "source_endpoint": "/api/estate",
            "snapshot_signature": "NOT_ESTABLISHED",
            "evidence_verification_scope": "collector_observation_only",
            "runtime_production_ready": "NOT_ESTABLISHED",
        },
        "authorization": {"mode": "READ_ONLY", "can_execute_actions": False, "human_approval": "NOT_ESTABLISHED"},
    }
    return {**body, "content_sha256": digest(body)}

"""Pure release dependency-loss rehearsal over the existing Command Center ontology.

Source collector metadata is *coverage*, never proof, authorization or quality.
The static nine release edges are required-but-UNPROVEN bindings, so closure
means structurally exposed to lost evidence, NOT demonstrated runtime failure.
One approved in-memory projection; no API calls, storage writes or scheduling.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import deque

from . import release_fabric as fabric

SCHEMA = "szl.readonly.release_impact.v1"
SELECTABLE = ("github", "huggingface", "cloudflare", "dns", "receipts")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
STATES = {"VERIFIED", "UNKNOWN", "UNAVAILABLE"}


def _digest(value: dict) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _validated(ontology: dict) -> tuple[list, dict, str]:
    if not isinstance(ontology, dict):
        raise ValueError("ONTOLOGY_REQUIRED")
    sha = ontology.get("source_snapshot_sha256")
    if type(sha) is not str or not SHA256.fullmatch(sha):
        raise ValueError("SOURCE_SNAPSHOT_UNQUALIFIED")
    nodes, graph = ontology.get("nodes"), ontology.get("release_fabric")
    if not isinstance(nodes, list) or len(nodes) != 6 or not isinstance(graph, dict):
        raise ValueError("SOURCE_GRAPH_UNAVAILABLE")
    # Validate the exact source projection emitted by backend.ontology.
    # These hashes are unsigned internal consistency checks, NOT authority.
    stamp = ontology.get("source_generated_at")
    if ("source_generated_at" not in ontology
            or (stamp is not None and
                (type(stamp) is not str or len(stamp) > 40))):
        raise ValueError("SOURCE_GENERATED_AT_INVALID")
    if nodes[0] != {
        "id": "snapshot:estate",
        "kind": "snapshot",
        "claim_scope": "projection_only",
        "action_authorized": False,
    }:
        raise ValueError("SNAPSHOT_NODE_INVALID")
    fields = {
        "id", "kind", "label", "truth_state", "reason_code",
        "observed_at", "evidence_ref_sha256", "claim_scope",
        "action_authorized",
    }
    reasons = {
        "DIRECT_OBSERVATION", "COLLECTOR_MISSING",
        "SNAPSHOT_STALE_OR_INVALID", "EVIDENCE_IDENTITY_MISSING",
        "OBSERVATION_STALE_OR_INVALID", "UPSTREAM_NOT_VERIFIED",
    }
    seen = {}
    for index, source in enumerate(SELECTABLE, start=1):
        node = nodes[index]
        if type(node) is not dict or set(node) != fields:
            raise ValueError("SOURCE_NODE_INVALID")
        state = node.get("truth_state")
        observed_at = node.get("observed_at")
        ref_hash = node.get("evidence_ref_sha256")
        if (node.get("id") != "source:" + source
                or node.get("kind") != "evidence_source"
                or node.get("label") != source
                or type(state) is not str or state not in STATES
                or node.get("reason_code") not in reasons
                or node.get("claim_scope") != "collector_observation_only"
                or node.get("action_authorized") is not False
                or (observed_at is not None and
                    (type(observed_at) is not str or len(observed_at) > 40))
                or (ref_hash is not None and
                    (type(ref_hash) is not str or not SHA256.fullmatch(ref_hash)))):
            raise ValueError("SOURCE_NODE_INVALID")
        seen[source] = state
    stages = graph.get("stages")
    edges = graph.get("dependencies")
    if (graph.get("schema") != fabric.SCHEMA
            or graph.get("basis_source_snapshot_sha256") != sha
            or graph.get("authority") != "READ_ONLY_NO_APPROVAL"
            or graph.get("production_qualified") is not False
            or graph.get("can_deploy") is not False
            or graph.get("financial_revenue_verified") is not False
            or graph.get("fingerprint_is_signature") is not False
            or graph.get("independently_qualified_stages") != 0
            or not isinstance(stages, list) or len(stages) != len(fabric.SOURCE_BINDINGS)
            or not isinstance(edges, list) or len(edges) != len(fabric.EDGES)):
        raise ValueError("RELEASE_FABRIC_UNQUALIFIED")
    for stage, (identity, collectors) in zip(stages, fabric.SOURCE_BINDINGS.items()):
        observed = [seen[collector] for collector in collectors]
        expected = ("UNAVAILABLE" if not observed or all(x == "UNAVAILABLE" for x in observed)
                    else "VERIFIED" if all(x == "VERIFIED" for x in observed)
                    else "UNKNOWN")
        if (not isinstance(stage, dict) or stage.get("id") != identity
                or stage.get("collectors") != list(collectors)
                or stage.get("collector_state") != expected
                or stage.get("collector_scope") != (
                    "EXISTING_METADATA_ONLY" if collectors else "NO_ADMITTED_COLLECTOR")
                or stage.get("qualification") != "NOT_ESTABLISHED"
                or stage.get("can_execute_actions") is not False):
            raise ValueError("RELEASE_FABRIC_STAGE_INVALID")
    for edge, (start, end, required) in zip(edges, fabric.EDGES):
        if (not isinstance(edge, dict) or
                (edge.get("source"), edge.get("target"), edge.get("required_binding"))
                != (start, end, required)
                or edge.get("evidence_state") != "NOT_ESTABLISHED"
                or edge.get("action_authorized") is not False):
            raise ValueError("RELEASE_FABRIC_EDGE_INVALID")
    observed_digest = graph.get("content_sha256")
    if type(observed_digest) is not str or not SHA256.fullmatch(observed_digest):
        raise ValueError("FABRIC_DIGEST_INVALID")
    body = {k: v for k, v in graph.items() if k != "content_sha256"}
    if _digest(body) != observed_digest:
        raise ValueError("FABRIC_DIGEST_MISMATCH")
    # Bind the graph to the SAME five observations as its claimed source SHA.
    # Rehashing only the release_fabric cannot update this independent basis.
    expected_basis = _digest({
        "source_generated_at": stamp,
        "observations": [
            (node["id"], node["truth_state"],
             node["observed_at"], node["evidence_ref_sha256"])
            for node in nodes[1:]
        ],
    })
    if expected_basis != sha:
        raise ValueError("SOURCE_SNAPSHOT_BASIS_MISMATCH")
    return nodes, graph, sha


def _closure(first: list[str]) -> list[str]:
    """Bounded topological reachability, not causal-effect proof."""
    stages = tuple(fabric.SOURCE_BINDINGS)
    adjacency = {name: [] for name in stages}
    for src, dst, _ in fabric.EDGES:
        if src not in adjacency or dst not in adjacency:
            raise ValueError("UNKNOWN_RELEASE_STAGE")
        if stages.index(src) >= stages.index(dst):
            raise ValueError("BACKWARD_EDGE_IN_GRAPH")
        adjacency[src].append(dst)
    seen = set()
    pending = deque(first)
    while pending:
        current = pending.popleft()
        if current in seen:
            continue
        if len(seen) >= len(stages):
            raise ValueError("GRAPH_CLOSURE_LIMIT")
        seen.add(current)
        pending.extend(adjacency[current])
    return [name for name in stages if name in seen]


def simulate(ontology: dict, source: str, expected_basis: str) -> dict:
    """One explicit non-authoritative withdrawal from a precomputed ontology."""
    if type(source) is not str or source not in SELECTABLE:
        raise ValueError("SOURCE_NOT_ALLOWED")
    nodes, original, basis = _validated(ontology)
    if type(expected_basis) is not str or not SHA256.fullmatch(expected_basis):
        raise ValueError("BASIS_INVALID")
    if basis != expected_basis:
        raise ValueError("SOURCE_SNAPSHOT_CHANGED")
    before = next(n["truth_state"] for n in nodes if n.get("id") == "source:" + source)
    selected = [stage for stage, collectors in fabric.SOURCE_BINDINGS.items()
                if source in collectors]
    # The original source SHA remains the basis for the *hypothetical* question;
    # re-projecting never writes back to that source or its original fingerprint.
    hypothetical_nodes = [
        {**n, "truth_state": "UNAVAILABLE"} if n.get("id") == "source:" + source else n
        for n in nodes
    ]
    hypothetical = fabric.project(hypothetical_nodes, basis)
    changes = [
        {"stage": old["id"], "before": old["collector_state"],
         "after": new["collector_state"]}
        for old, new in zip(original["stages"], hypothetical["stages"])
        if old["collector_state"] != new["collector_state"]
    ]
    closure = _closure(selected)
    # These edges are already unproved. Exposure is not actual failure.
    graph_exposure = [
        {"source": start, "target": end, "required_binding": reason,
         "binding_verified": False}
        for start, end, reason in fabric.EDGES if start in closure and end in closure
    ]
    body = {
        "schema": SCHEMA,
        "mode": "HYPOTHETICAL_EVIDENCE_WITHDRAWAL",
        "basis_source_snapshot_sha256": basis,
        "basis_release_fabric_sha256": original["content_sha256"],
        "selected_source": source,
        "source_observation_before": before,
        "source_observation_assumed_after": "UNAVAILABLE",
        "observation_changed": before != "UNAVAILABLE",
        "collector_stage_changes": changes,
        "structurally_exposed_stages": closure,
        "structurally_exposed_edges": graph_exposure,
        "collector_changes_count": len(changes),
        "exposed_stage_count": len(closure),
        "required_proof_state": "NOT_ESTABLISHED",
        "source_modified": False,
        "provider_state_changed": False,
        "production_qualified": False,
        "action_authorized": False,
        "can_deploy": False,
        "model_quality_verified": False,
        "settlement_verified": False,
        "fingerprint_is_signature": False,
        "interpretation": (
            "A bounded dependency-loss rehearsal over existing collector metadata. "
            "Exposed stages are theoretical prerequisite paths, not observed failures. "
            "No provider identities, model proofs, production, payment or authorization "
            "are admitted by this view."
        ),
    }
    return {**body, "content_sha256": _digest(body)}

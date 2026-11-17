"""Read-only release-evidence dependency graph from Command Center's existing ontology.

This is a *projection*, not a new collector, workflow scheduler, payment
instrument, external probe, controller, authorization gate or runtime proof.
It never reads arbitrary collector.value, URLs, credentials or secret payloads.
Every unproved release binding remains unqualified even if collector metadata
was successfully observed.
"""

from __future__ import annotations

import hashlib
import json

SCHEMA = "szl.readonly.release_fabric.v1"
SOURCE_BINDINGS = {
    "github_source": ("github",),
    "hf_catalog": ("huggingface",),
    "cloudflare_edge": ("cloudflare", "dns"),
    "receipt_index": ("receipts",),
    "model_evaluation": (),
    "runtime_deployment": (),
    "payment_settlement": (),
    "pypi_distribution": (),
}
GATES = {
    "github_source": "IMMUTABLE_SOURCE_CHECKS_AND_REVIEW",
    "hf_catalog": "PINNED_MODEL_AND_DATASET_ARTIFACT_BYTES",
    "cloudflare_edge": "EXACT_DEPLOYMENT_AND_RULE_READBACK",
    "receipt_index": "INDEPENDENTLY_VERIFIED_RECEIPT_AUTHORITY",
    "model_evaluation": "WEIGHT_BOUND_MEASUREMENTS_AND_BASELINES",
    "runtime_deployment": "SOURCE_MATCHED_EXTERNAL_RUNTIME_AND_AUTH",
    "payment_settlement": "FACILITATOR_CHAIN_AND_PAYOUT_RECONCILIATION",
    "pypi_distribution": "PEP740_WHEEL_SDIST_TAG_AND_SOURCE_MATCH",
}
EDGES = (
    ("github_source", "hf_catalog", "GITHUB_TO_HF_ARTIFACT_BINDING"),
    ("github_source", "cloudflare_edge", "SOURCE_TO_EDGE_CONFIG_BINDING"),
    ("github_source", "pypi_distribution", "SOURCE_TO_PACKAGE_PROVENANCE_BINDING"),
    ("hf_catalog", "model_evaluation", "WEIGHTS_TO_EVALUATION_BINDING"),
    ("hf_catalog", "runtime_deployment", "WEIGHTS_TO_RUNTIME_BINDING"),
    ("cloudflare_edge", "runtime_deployment", "EDGE_TO_RUNTIME_IDENTITY_BINDING"),
    ("receipt_index", "model_evaluation", "RECEIPT_TO_EVALUATION_BINDING"),
    ("receipt_index", "payment_settlement", "RECEIPT_TO_SETTLEMENT_BINDING"),
    ("runtime_deployment", "payment_settlement", "RUNTIME_TO_SETTLEMENT_BINDING"),
)
_STATES = {"VERIFIED", "UNKNOWN", "UNAVAILABLE"}


def _hash(value: dict) -> str:
    """Deterministic content fingerprint, explicitly not an attestation."""
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def project(ontology_nodes, source_snapshot_sha256: str) -> dict:
    """Project graph topology and evidence *coverage* without promoting claims.

    Only the ontology's already-normalized truth states are used. VERIFIED means
    a collector observation was admitted, not a qualified source/model/release.
    """
    source_states = {}
    if isinstance(ontology_nodes, list) and len(ontology_nodes) <= 20:
        for node in ontology_nodes:
            if not isinstance(node, dict):
                continue
            identifier, state = node.get("id"), node.get("truth_state")
            if (
                type(identifier) is str
                and identifier.startswith("source:")
                and identifier[7:] in {"github", "huggingface", "cloudflare", "dns", "receipts"}
                and type(state) is str
                and state in _STATES
                and identifier not in source_states
            ):
                source_states[identifier] = state
    if (
        not isinstance(source_snapshot_sha256, str)
        or len(source_snapshot_sha256) != 64
        or any(c not in "0123456789abcdef" for c in source_snapshot_sha256)
    ):
        raise ValueError("source snapshot fingerprint must be a lowercase SHA-256")
    stages = []
    for stage, sources in SOURCE_BINDINGS.items():
        states = [source_states.get("source:" + name, "UNAVAILABLE") for name in sources]
        if not states or all(s == "UNAVAILABLE" for s in states):
            observed = "UNAVAILABLE"
        elif all(s == "VERIFIED" for s in states):
            observed = "VERIFIED"
        else:
            observed = "UNKNOWN"
        stages.append(
            {
                "id": stage,
                "kind": "release_stage",
                "collector_state": observed,
                "collector_scope": "EXISTING_METADATA_ONLY" if sources else "NO_ADMITTED_COLLECTOR",
                "collectors": list(sources),
                "required_gate": GATES[stage],
                "qualification": "NOT_ESTABLISHED",
                "can_execute_actions": False,
            }
        )
    dependencies = [
        {
            "source": source,
            "target": target,
            "required_binding": reason,
            "evidence_state": "NOT_ESTABLISHED",
            "action_authorized": False,
        }
        for source, target, reason in EDGES
    ]
    body = {
        "schema": SCHEMA,
        "scope": "SOURCE_COVERAGE_AND_RELEASE_REQUIREMENTS_ONLY",
        "basis_source_snapshot_sha256": source_snapshot_sha256,
        "stages": stages,
        "dependencies": dependencies,
        "stage_count": len(stages),
        "collector_verified_stages": sum(s["collector_state"] == "VERIFIED" for s in stages),
        "independently_qualified_stages": 0,
        "unverified_dependency_count": len(dependencies),
        "production_qualified": False,
        "can_deploy": False,
        "financial_revenue_verified": False,
        "authority": "READ_ONLY_NO_APPROVAL",
        "fingerprint_is_signature": False,
        "limitations": (
            "Static dependencies are not observed source-to-target edges. "
            "Collector VERIFIED means current collector metadata only, "
            "not artifact integrity, runtime parity, evaluated model quality, "
            "Cloudflare payment settlement or attested PyPI publication. "
            "Missing independent proof remains NOT_ESTABLISHED."
        ),
    }
    return {**body, "content_sha256": _hash(body)}

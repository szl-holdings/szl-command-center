# SPDX-License-Identifier: Apache-2.0
"""Operator-only SZL Lake evidence graph readback, no hosted API routes.

Canonical owner: szl-holdings/szl-lake (szl.lake.evidence-graph/v1).
Only explicit loopback is allowed. This code is never imported by the
Command Center web application and deliberately performs zero requests
without a CLI invocation. It does NOT grant production, signer, tenant,
payment, deployment or training authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping

MAX_BODY_BYTES = 1024 * 1024
MAX_SOURCE_RECEIPTS = 10_000
MAX_ORGANS = 128
SHA3 = re.compile(r"[0-9a-f]{64}\Z")
ORGAN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
SCHEMA = "szl.lake.evidence-graph/v1"
SQL_SCHEMA = "szl.lake.sql-summary/v1"
FALSE_FLAGS = (
    "graph_checksum_signed",
    "independent_chain_heads_verified",
    "issuer_signatures_verified",
    "origin_authentication_verified",
    "tenant_authorization_verified",
    "causal_inference_performed",
    "model_training_authorized",
)
EXPECTED_TOP_LEVEL = frozenset({
    "schema", "state", "projection", "claim_scope", "schema_semantics",
    "source", "graph", "distributions", "graph_sha3_256",
    "limits", "external_effects", "backend_writes", *FALSE_FLAGS,
})


class BridgeRefusal(ValueError):
    """Finite error codes without data from the rejected upstream payload."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BridgeRefusal("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _json_parse(body: bytes):
    try:
        doc = json.loads(
            body.decode("utf-8"), object_pairs_hook=_object_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                BridgeRefusal("INVALID_JSON_CONSTANT")
            ),
        )
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, BridgeRefusal):
            raise
        raise BridgeRefusal("INVALID_JSON") from None
    if not isinstance(doc, dict):
        raise BridgeRefusal("GRAPH_NOT_OBJECT")
    return doc


def _integer(value, upper=MAX_SOURCE_RECEIPTS):
    return type(value) is int and 0 <= value <= upper


def validate(document: Mapping) -> dict:
    """Recompute checksum and source arithmetic without asserting authenticity."""
    if not isinstance(document, Mapping) or set(document) != EXPECTED_TOP_LEVEL:
        raise BridgeRefusal("UNEXPECTED_SCHEMA_FIELDS")
    if document.get("schema") != SCHEMA:
        raise BridgeRefusal("SCHEMA_MISMATCH")
    if (document.get("projection") != "READ_ONLY_EPHEMERAL"
            or document.get("claim_scope") != "LOCAL_CHAIN_INTEGRITY_ONLY"):
        raise BridgeRefusal("SOURCE_SCOPE_NOT_ADMITTED")
    if any(document.get(k) is not False for k in FALSE_FLAGS):
        raise BridgeRefusal("UNPROVED_AUTHORITY_CLAIMED")
    if document.get("external_effects") != 0 or document.get("backend_writes") != 0:
        raise BridgeRefusal("EFFECTS_NOT_ZERO")
    source, graph, dists = document.get("source"), document.get("graph"), document.get("distributions")
    if (not isinstance(source, dict) or not isinstance(graph, dict)
            or not isinstance(dists, list) or set(graph) != {"nodes", "edges"}
            or not isinstance(graph["nodes"], list)
            or not isinstance(graph["edges"], list)):
        raise BridgeRefusal("GRAPH_SHAPE_INVALID")
    if (source.get("schema") != SQL_SCHEMA
            or source.get("name") != "szl_lake_sql.summarize"
            or set(source) != {"schema", "name", "source_heads", "total_receipts",
                               "selected_receipts", "organ_filter"}):
        raise BridgeRefusal("SOURCE_SHAPE_INVALID")
    total, selected = source["total_receipts"], source["selected_receipts"]
    if not _integer(total) or not _integer(selected) or selected > total:
        raise BridgeRefusal("DENOMINATOR_INVALID")
    if document.get("state") != ("EMPTY" if total == 0 else "LOCAL_CHAIN_VALIDATED"):
        raise BridgeRefusal("OBSERVATION_STATE_INVALID")
    selector = source["organ_filter"]
    if selector is not None and (type(selector) is not str or ORGAN.fullmatch(selector) is None):
        raise BridgeRefusal("SELECTOR_INVALID")
    heads = source["source_heads"]
    if not isinstance(heads, list) or len(heads) > MAX_ORGANS or len(dists) > MAX_ORGANS:
        raise BridgeRefusal("SOURCE_COVERAGE_INVALID")
    head_counts = {}
    for item in heads:
        if not isinstance(item, dict) or set(item) != {"organ", "count", "chain_index", "chain_head"}:
            raise BridgeRefusal("HEAD_SHAPE_INVALID")
        organ = item["organ"]
        if (type(organ) is not str or not ORGAN.fullmatch(organ)
                or organ in head_counts or (selector is not None and organ != selector)
                or not _integer(item["count"]) or item["count"] == 0
                or type(item["chain_index"]) is not int
                or item["chain_index"] != item["count"]
                or type(item["chain_head"]) is not str
                or SHA3.fullmatch(item["chain_head"]) is None):
            raise BridgeRefusal("HEAD_SHAPE_INVALID")
        head_counts[organ] = item["count"]
    dist_counts = {}
    for row in dists:
        if not isinstance(row, dict) or set(row) != {
            "organ", "count", "decision_entropy_bits", "decision_frequencies"
        }:
            raise BridgeRefusal("DISTRIBUTION_INVALID")
        organ = row["organ"]
        entries = row["decision_frequencies"]
        if (type(organ) is not str or organ not in head_counts
                or organ in dist_counts or not _integer(row["count"])
                or row["count"] != head_counts[organ]
                or not isinstance(entries, list) or not entries or len(entries) > 10):
            raise BridgeRefusal("DISTRIBUTION_INVALID")
        parts = 0
        decisions = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {
                "decision", "count", "fraction_of_organ"
            }:
                raise BridgeRefusal("DISTRIBUTION_INVALID")
            decision = entry["decision"]
            if (type(decision) is not str or not re.fullmatch(r"[A-Z_]+", decision)
                    or decision in decisions or not _integer(entry["count"])
                    or entry["count"] == 0
                    or type(entry["fraction_of_organ"]) not in (float, int)
                    or not 0 <= entry["fraction_of_organ"] <= 1):
                raise BridgeRefusal("DISTRIBUTION_INVALID")
            decisions.add(decision)
            parts += entry["count"]
        if parts != row["count"]:
            raise BridgeRefusal("DENOMINATOR_INVALID")
        dist_counts[organ] = row["count"]
    if head_counts != dist_counts or sum(dist_counts.values()) != selected:
        raise BridgeRefusal("SOURCE_HEAD_MISMATCH")
    if selector is None and total != selected:
        raise BridgeRefusal("SOURCE_COVERAGE_INVALID")
    nodes, edges = graph["nodes"], graph["edges"]
    if len(nodes) > 1 + MAX_ORGANS * 11 or len(edges) > MAX_ORGANS * 11:
        raise BridgeRefusal("GRAPH_SIZE_INVALID")
    ids = set()
    snapshot_nodes = 0
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"id", "kind", "label", "count"}:
            raise BridgeRefusal("NODE_SHAPE_INVALID")
        nid = node["id"]
        if (type(nid) is not str or nid in ids or not _integer(node["count"])
                or type(node["label"]) is not str or len(node["label"]) > 128):
            raise BridgeRefusal("NODE_SHAPE_INVALID")
        if nid == "lake:validated-snapshot":
            snapshot_nodes += 1
            if node["kind"] != "SOURCE_SNAPSHOT" or node["count"] != total:
                raise BridgeRefusal("NODE_SHAPE_INVALID")
        elif nid.startswith("organ:"):
            if node["kind"] != "ORGAN" or nid[6:] not in head_counts:
                raise BridgeRefusal("NODE_SHAPE_INVALID")
        elif nid.startswith("decision:"):
            if node["kind"] != "DECISION_CLASS":
                raise BridgeRefusal("NODE_SHAPE_INVALID")
        else:
            raise BridgeRefusal("NODE_SHAPE_INVALID")
        ids.add(nid)
    if snapshot_nodes != 1:
        raise BridgeRefusal("NODE_SHAPE_INVALID")
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("type") != "AGGREGATED_FROM":
            raise BridgeRefusal("EDGE_SHAPE_INVALID")
        if (edge.get("from") not in ids or edge.get("to") not in ids
                or not _integer(edge.get("count"))
                or type(edge.get("fraction_of_organ", edge.get("fraction_of_source"))) not in (int, float)):
            raise BridgeRefusal("EDGE_SHAPE_INVALID")

    stable = {
        "nodes": nodes, "edges": edges, "distributions": dists,
        "source_heads": heads, "total_source_receipts": total,
        "selected_receipts": selected, "organ_filter": selector,
    }
    try:
        canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError):
        raise BridgeRefusal("GRAPH_NOT_CANONICAL") from None
    calculated = hashlib.sha3_256(canonical).hexdigest()
    if document["graph_sha3_256"] != calculated:
        raise BridgeRefusal("GRAPH_CHECKSUM_MISMATCH")
    return {
        "state": "LOCAL_CHECKSUM_CONSISTENT" if total else "EMPTY_UNOBSERVED",
        "source_scope": "LOOPBACK_ONLY_OWNER_DECLARED",
        "schema": SCHEMA,
        "total_source_receipts": total,
        "selected_receipts": selected,
        "organ_nodes": len(head_counts),
        "graph_nodes": len(nodes),
        "graph_edges": len(edges),
        "graph_sha3_256": calculated,
        "provider_source_issuer_verified": False,
        "independent_signed_receipt_verified": False,
        "privacy_access_verified": False,
        "production_ready": False,
        "can_train": False,
        "can_publish": False,
        "can_execute_actions": False,
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_local(*, port: int = 8088, organ: str | None = None, opener=None) -> dict:
    """GET an exact-origin, no-credential local Lake graph readback only."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise BridgeRefusal("PORT_INVALID")
    if organ is not None and (type(organ) is not str or ORGAN.fullmatch(organ) is None):
        raise BridgeRefusal("SELECTOR_INVALID")
    from .public_preview import active
    if active():
        raise BridgeRefusal("PUBLIC_PREVIEW_NOT_ADMITTED")
    url = "http://127.0.0.1:" + str(port) + "/api/lake/v1/graph/summary"
    if organ is not None:
        url += "?organ=" + urllib.parse.quote(organ, safe="")
    request = urllib.request.Request(
        url, headers={"Accept": "application/json",
                      "User-Agent": "szl-operator-local-graph/1"},
        method="GET",
    )
    reader = opener if opener is not None else urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect()
    ).open
    try:
        with reader(request, timeout=5) as reply:
            if reply.status != 200:
                raise BridgeRefusal("LAKE_NOT_HTTP_200")
            if reply.geturl() != url:
                raise BridgeRefusal("URL_REDIRECT_REFUSED")
            if reply.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
                raise BridgeRefusal("NON_JSON_RESPONSE")
            if reply.headers.get("Cache-Control", "").lower() != "no-store":
                raise BridgeRefusal("CACHE_BOUNDARY_UNOBSERVED")
            body = reply.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise BridgeRefusal("LAKE_HTTP_" + str(exc.code)) from None
    except (OSError, TimeoutError, ValueError) as exc:
        if isinstance(exc, BridgeRefusal):
            raise
        raise BridgeRefusal("LAKE_UNREACHABLE") from None
    if not body or len(body) > MAX_BODY_BYTES:
        raise BridgeRefusal("GRAPH_RESPONSE_SIZE_INVALID")
    return validate(_json_parse(body))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Operator-local graph readback, not a hosted service")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--organ", default=None)
    args = parser.parse_args(argv)
    try:
        result = read_local(port=args.port, organ=args.organ)
    except BridgeRefusal as exc:
        result = {"state": "HOLD", "code": exc.code, "production_ready": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if result["state"] in ("LOCAL_CHECKSUM_CONSISTENT", "EMPTY_UNOBSERVED") else 2


if __name__ == "__main__":
    raise SystemExit(main())

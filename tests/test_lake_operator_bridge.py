# SPDX-License-Identifier: Apache-2.0
"""Local-only Lake bridge: no real network, secrets, provider writes or public routes."""
import hashlib
import http.client
import json
from unittest.mock import patch
import urllib.error

import pytest

from backend import lake_operator_bridge as bridge


def graph_fixture():
    heads = [
        {"organ": "audit", "count": 2, "chain_index": 2, "chain_head": "a" * 64},
        {"organ": "model", "count": 1, "chain_index": 1, "chain_head": "b" * 64},
    ]
    nodes = [
        {"id": "lake:validated-snapshot", "kind": "SOURCE_SNAPSHOT",
         "count": 3, "label": "Validated local ledger projection"},
        {"id": "organ:audit", "kind": "ORGAN", "count": 2, "label": "audit"},
        {"id": "organ:model", "kind": "ORGAN", "count": 1, "label": "model"},
        {"id": "decision:audit:ALLOW", "kind": "DECISION_CLASS", "count": 1, "label": "ALLOW"},
        {"id": "decision:audit:DENY", "kind": "DECISION_CLASS", "count": 1, "label": "DENY"},
        {"id": "decision:model:UNKNOWN", "kind": "DECISION_CLASS", "count": 1, "label": "UNKNOWN"},
    ]
    edges = [
        {"from": "organ:audit", "to": "lake:validated-snapshot", "type": "AGGREGATED_FROM",
         "count": 2, "fraction_of_source": 0.666667},
        {"from": "organ:model", "to": "lake:validated-snapshot", "type": "AGGREGATED_FROM",
         "count": 1, "fraction_of_source": 0.333333},
        {"from": "decision:audit:ALLOW", "to": "organ:audit", "type": "AGGREGATED_FROM",
         "count": 1, "fraction_of_organ": 0.5},
        {"from": "decision:audit:DENY", "to": "organ:audit", "type": "AGGREGATED_FROM",
         "count": 1, "fraction_of_organ": 0.5},
        {"from": "decision:model:UNKNOWN", "to": "organ:model", "type": "AGGREGATED_FROM",
         "count": 1, "fraction_of_organ": 1.0},
    ]
    distributions = [
        {"organ": "audit", "count": 2, "decision_entropy_bits": 1.0,
         "decision_frequencies": [
             {"decision": "ALLOW", "count": 1, "fraction_of_organ": 0.5},
             {"decision": "DENY", "count": 1, "fraction_of_organ": 0.5},
         ]},
        {"organ": "model", "count": 1, "decision_entropy_bits": 0.0,
         "decision_frequencies": [
             {"decision": "UNKNOWN", "count": 1, "fraction_of_organ": 1.0},
         ]},
    ]
    source = {
        "schema": bridge.SQL_SCHEMA, "name": "szl_lake_sql.summarize",
        "source_heads": heads, "total_receipts": 3,
        "selected_receipts": 3, "organ_filter": None,
    }
    result = {
        "schema": bridge.SCHEMA, "state": "LOCAL_CHAIN_VALIDATED",
        "projection": "READ_ONLY_EPHEMERAL",
        "claim_scope": "LOCAL_CHAIN_INTEGRITY_ONLY",
        "schema_semantics": "SZL_PRIVATE_AGGREGATED_FROM_V1_NOT_PROV_O_CONFORMANCE",
        "source": source, "graph": {"nodes": nodes, "edges": edges},
        "distributions": distributions, "limits": "synthetic fixture only",
        "external_effects": 0, "backend_writes": 0,
        **{name: False for name in bridge.FALSE_FLAGS},
    }
    stable = {
        "nodes": nodes, "edges": edges, "distributions": distributions,
        "source_heads": heads, "total_source_receipts": 3,
        "selected_receipts": 3, "organ_filter": None,
    }
    raw = json.dumps(stable, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("utf-8")
    result["graph_sha3_256"] = hashlib.sha3_256(raw).hexdigest()
    return result


def test_same_source_shape_recomputed_and_truth_bounded():
    value = bridge.validate(graph_fixture())
    assert value["state"] == "LOCAL_CHECKSUM_CONSISTENT"
    assert value["total_source_receipts"] == 3
    assert value["selected_receipts"] == 3
    assert value["organ_nodes"] == 2
    assert value["graph_nodes"] == 6
    assert value["graph_edges"] == 5
    assert all(value[key] is False for key in (
        "provider_source_issuer_verified", "independent_signed_receipt_verified",
        "privacy_access_verified", "production_ready", "can_train",
        "can_publish", "can_execute_actions",
    ))


@pytest.mark.parametrize("mutator,reason", [
    (lambda x: x.update({"graph_sha3_256": "0" * 64}), "GRAPH_CHECKSUM_MISMATCH"),
    (lambda x: x.update({"issuer_signatures_verified": True}), "UNPROVED_AUTHORITY_CLAIMED"),
    (lambda x: x.update({"production_qualified": True}), "UNEXPECTED_SCHEMA_FIELDS"),
    (lambda x: x["source"].update({"selected_receipts": 2}), "SOURCE_HEAD_MISMATCH"),
    (lambda x: x["source"]["source_heads"][0].update({"chain_head": "forged"}), "HEAD_SHAPE_INVALID"),
    (lambda x: x["source"]["source_heads"][1].update({"chain_index": True}), "HEAD_SHAPE_INVALID"),
    (lambda x: x["distributions"][0]["decision_frequencies"][0].update({"count": 2}), "DENOMINATOR_INVALID"),
    (lambda x: x["graph"]["nodes"][0].update({"receipt": "DO_NOT_LEAK"}), "NODE_SHAPE_INVALID"),
    (lambda x: x["graph"]["edges"][0].update({"type": "CAUSES"}), "EDGE_SHAPE_INVALID"),
])
def test_forged_evidence_or_denominators_fail_closed(mutator, reason):
    data = graph_fixture()
    mutator(data)
    with pytest.raises(bridge.BridgeRefusal) as error:
        bridge.validate(data)
    assert error.value.code == reason
    assert "DO_NOT_LEAK" not in str(error.value)


def test_reject_ambiguous_json_without_printing_values():
    with pytest.raises(bridge.BridgeRefusal) as error:
        bridge._json_parse(b'{"schema":"expected","schema":"forged","private":"SECRET"}')
    assert error.value.code == "DUPLICATE_JSON_KEY"
    assert "SECRET" not in str(error.value)


class _Response:
    def __init__(self, req, *, status=200, body=None, content_type="application/json",
                 cache_control="no-store", final_url=None):
        self.status = status
        self.body = body if body is not None else json.dumps(graph_fixture()).encode()
        self.url = req.full_url if final_url is None else final_url
        self.headers = {
            "Content-Type": content_type,
            "Cache-Control": cache_control,
        }

    def geturl(self):
        return self.url

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_reader_gets_only_exact_local_api_with_no_secrets():
    seen = []
    def opener(req, *, timeout):
        assert timeout == 5
        assert req.get_method() == "GET"
        assert req.full_url == "http://127.0.0.1:8088/api/lake/v1/graph/summary"
        assert req.get_header("Authorization") is None
        assert req.get_header("Cookie") is None
        seen.append(True)
        return _Response(req)
    with patch("backend.public_preview.active", return_value=False):
        result = bridge.read_local(opener=opener)
    assert seen == [True]
    assert result["state"] == "LOCAL_CHECKSUM_CONSISTENT"
    assert result["production_ready"] is False


def test_reader_refuses_public_preview_before_contacting_ledger():
    def forbidden(*_args, **_kwargs):
        raise AssertionError("should never call network")
    with patch("backend.public_preview.active", return_value=True):
        with pytest.raises(bridge.BridgeRefusal) as error:
            bridge.read_local(opener=forbidden)
    assert error.value.code == "PUBLIC_PREVIEW_NOT_ADMITTED"


@pytest.mark.parametrize("port", [0, 65536, -1, "8088", True, None])
def test_no_uncontrolled_endpoint_or_port(port):
    with pytest.raises(bridge.BridgeRefusal) as error:
        bridge.read_local(port=port)
    assert error.value.code == "PORT_INVALID"


@pytest.mark.parametrize("organ", ["../audit", "a/b", "a?x=1", "", "A", True])
def test_no_unsafe_organ_path(organ):
    with pytest.raises(bridge.BridgeRefusal) as error:
        bridge.read_local(organ=organ)
    assert error.value.code == "SELECTOR_INVALID"


@pytest.mark.parametrize("kind,reason", [
    ("redirect", "URL_REDIRECT_REFUSED"),
    ("media", "NON_JSON_RESPONSE"),
    ("cache", "CACHE_BOUNDARY_UNOBSERVED"),
    ("large", "GRAPH_RESPONSE_SIZE_INVALID"),
    ("http", "LAKE_HTTP_503"),
    ("network", "LAKE_UNREACHABLE"),
])
def test_http_data_path_fails_closed(kind, reason):
    def opener(req, *, timeout):
        if kind == "http":
            raise urllib.error.HTTPError(req.full_url, 503, "unavailable", http.client.HTTPMessage(), None)
        if kind == "network":
            raise OSError("secret private path")
        return _Response(
            req,
            final_url="https://external.example/" if kind == "redirect" else None,
            content_type="text/html" if kind == "media" else "application/json",
            cache_control="public" if kind == "cache" else "no-store",
            body=b"x" * (bridge.MAX_BODY_BYTES + 1) if kind == "large" else None,
        )
    with patch("backend.public_preview.active", return_value=False):
        with pytest.raises(bridge.BridgeRefusal) as exc:
            bridge.read_local(opener=opener)
    assert exc.value.code == reason
    assert "secret" not in str(exc.value)


def test_no_hosted_route_or_private_ledger_imports_in_web_app():
    from backend import main
    paths = {r.path for r in main.app.routes if hasattr(r, "path")}
    assert "/api/lake-graph" not in paths
    assert "/api/lake/v1/graph/summary" not in paths
    assert "/api/estate" in paths
    assert "/api/ontology" in paths

"""Temporal source/runtime witness for the SZL Command Center.

Samples GitHub protected main before and after fixed, read-only HTTPS
observations of both A11oy origins. A source declaration is NOT a byte-level
deployment proof. No provider writes, credentials, or release approval.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Callable
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

SCHEMA = "szl.temporal-convergence-observation/v1"
REPOSITORY = "szl-holdings/a11oy"
ORIGINS = ("https://szlholdings-a11oy.hf.space", "https://a-11-oy.com")
ROUTES = {
    "build": "/api/build-info",
    "storage": "/api/a11oy/v1/storage/status",
    "health": "/api/a11oy/healthz",
}
STORES = frozenset(("gdw", "khipu", "khipu_council", "khipu_lmdb",
                    "khipu_repl", "series_a", "unay"))
MAX_RESPONSE = 262144
MAX_MAIN_RESPONSE = 32768
GITHUB_MAIN_URL = "https://api.github.com/repos/szl-holdings/a11oy/branches/main"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class InvalidObservation(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidObservation("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _parse(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE:
        raise InvalidObservation("INVALID_BODY_SIZE")
    value = json.loads(
        raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
        parse_constant=lambda v: (_ for _ in ()).throw(
            InvalidObservation("NONFINITE_JSON")))
    if type(value) is not dict:
        raise InvalidObservation("OBJECT_REQUIRED")
    return value


def _get(url):
    # Callers cannot override these fixed HTTPS route targets from requests.
    if url not in {origin + route for origin in ORIGINS
                   for route in ROUTES.values()}:
        raise InvalidObservation("FOREIGN_TARGET")
    request = Request(url, method="GET", headers={
        "Accept": "application/json", "Cache-Control": "no-cache",
        "User-Agent": "szl-convergence-witness/1",
    })
    with build_opener(NoRedirect()).open(request, timeout=10) as response:
        if response.status != 200 or response.geturl() != url:
            raise InvalidObservation("HTTP_OR_REDIRECT_DENIED")
        if "application/json" not in response.headers.get("Content-Type", "").lower():
            raise InvalidObservation("CONTENT_TYPE_NOT_JSON")
        body = response.read(MAX_RESPONSE + 1)
    _parse(body)
    return body


def _head():
    """Read protected GitHub main via stdlib HTTPS, independent of gh.

    The host, path, body size, branch identity and protected flag are pinned.
    Invalid authentication, rate limits and redirects fail closed, without
    retrying anonymously or treating a stale source revision as main.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Cache-Control": "no-cache",
        "User-Agent": "szl-convergence-witness/1",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(GITHUB_MAIN_URL, method="GET", headers=headers)
    with build_opener(NoRedirect()).open(request, timeout=10) as response:
        if response.status != 200 or response.geturl() != GITHUB_MAIN_URL:
            raise InvalidObservation("GITHUB_MAIN_HTTP_OR_REDIRECT_DENIED")
        media_type = response.headers.get("Content-Type", "").lower()
        if not ("application/json" in media_type or
                "application/vnd.github+json" in media_type):
            raise InvalidObservation("GITHUB_MAIN_JSON_REQUIRED")
        raw = response.read(MAX_MAIN_RESPONSE + 1)
    if len(raw) > MAX_MAIN_RESPONSE:
        raise InvalidObservation("GITHUB_MAIN_BODY_TOO_LARGE")
    data = _parse(raw)
    commit = data.get("commit")
    sha = commit.get("sha") if type(commit) is dict else None
    if (data.get("name") != "main" or data.get("protected") is not True
            or type(sha) is not str or not SHA40.fullmatch(sha)):
        raise InvalidObservation("GITHUB_MAIN_PROTECTED_SHA_UNVERIFIED")
    return sha


def _reported_revision(doc):
    build = doc.get("build") if type(doc) is dict else None
    if type(build) is not dict:
        return None
    fields = build.get("field_evidence")
    sha = build.get("revision")
    if (doc.get("status") != "OBSERVED" or type(fields) is not dict
            or fields.get("revision") != "OBSERVED"
            or type(sha) is not str or not SHA40.fullmatch(sha)):
        return None
    return sha


def _store_check(doc):
    failures = []
    if type(doc) is not dict:
        return False, ["STORAGE_MISSING"], {
            "epoch": None, "sequence": None, "heartbeat_age_s": None,
            "healthy_stores": 0, "required_stores": len(STORES),
        }
    lease = doc.get("lease")
    stores = doc.get("stores")
    if type(lease) is not dict:
        lease = {}
    if type(stores) is not dict:
        stores = {}
    age = lease.get("heartbeat_age_s")
    epoch = doc.get("epoch")
    sequence = lease.get("sequence")
    if (doc.get("schema") != "szl.a11oy-storage-status/v2"
            or doc.get("mode") != "FENCED" or doc.get("role") != "WRITER"
            or doc.get("claim") != "CLEAN" or doc.get("writable") is not True
            or lease.get("state") != "ACTIVE"
            or type(epoch) is not int or epoch < 1
            or type(sequence) is not int or sequence < 1
            or type(age) not in (int, float)
            or not math.isfinite(age) or not 0 <= age <= 60):
        failures.append("WRITER_LEASE_NOT_QUALIFIED")
    if doc.get("alert") is not False:
        failures.append("STORAGE_ALERT")
    if doc.get("pending_publish") != [] or doc.get("active_errors") != {}:
        failures.append("STORAGE_PENDING_OR_ERRORS")
    if set(stores) != STORES:
        failures.append("REQUIRED_STORE_SET_MISMATCH")
    for name in STORES:
        item = stores.get(name)
        if (type(item) is not dict or item.get("health") != "OK"
                or item.get("origin") != "RESTORED"
                or type(item.get("snapshot_failures")) is not int
                or item["snapshot_failures"] != 0
                or item.get("last_error_code") is not None):
            failures.append("STORE_UNHEALTHY_" + name.upper())
    metadata = {
        "epoch": epoch if type(epoch) is int else None,
        "sequence": sequence if type(sequence) is int else None,
        "heartbeat_age_s": age if type(age) in (int, float)
                           and math.isfinite(age) else None,
        "healthy_stores": sum(type(stores.get(name)) is dict
                              and stores[name].get("health") == "OK"
                              for name in STORES),
        "required_stores": len(STORES),
    }
    return not failures, sorted(set(failures)), metadata


def collect(*, head_reader: Callable[[], str] | None = None,
            fetcher: Callable[[str], bytes] | None = None,
            clock: Callable[[], str] | None = None):
    """Bounded, cached-at-route snapshot with a main-before/main-after fence."""
    head_reader = head_reader or _head
    fetcher = fetcher or _get
    clock = clock or now_utc
    started_at = clock()
    blockers, evidence, samples = [], [], {}

    def head(phase):
        try:
            sha = head_reader()
            if type(sha) is not str or not SHA40.fullmatch(sha):
                raise InvalidObservation("INVALID_SHA")
            return sha
        except Exception:
            blockers.append("GITHUB_MAIN_" + phase + "_UNAVAILABLE")
            return None

    before = head("BEFORE")
    for origin in ORIGINS:
        samples[origin] = {}
        for kind, route in ROUTES.items():
            if kind == "health" and origin != ORIGINS[0]:
                continue
            url = origin + route
            try:
                raw = fetcher(url)
                doc = _parse(raw)
                samples[origin][kind] = doc
                evidence.append({"origin": origin, "path": route,
                                 "state": "OBSERVED",
                                 "body_sha256": hashlib.sha256(raw).hexdigest()})
            except HTTPError as exc:
                blockers.append("HTTP_" + str(exc.code) + "_" + kind.upper())
                evidence.append({"origin": origin, "path": route,
                                 "state": "UNAVAILABLE", "code": "HTTP_" + str(exc.code)})
            except Exception:
                blockers.append("OBSERVATION_UNAVAILABLE_" + kind.upper())
                evidence.append({"origin": origin, "path": route,
                                 "state": "UNAVAILABLE"})
    after = head("AFTER")
    declared = {origin: _reported_revision(samples[origin].get("build"))
                for origin in ORIGINS}
    if before is None or after is None:
        source = "UNKNOWN"
    elif before != after:
        source = "MAIN_MOVED"
        blockers.append("MAIN_CHANGED_DURING_CAPTURE")
    elif any(value is None for value in declared.values()):
        source = "UNKNOWN"
        blockers.append("SOURCE_DECLARATION_UNAVAILABLE")
    elif all(value == after for value in declared.values()):
        source = "DECLARATIONS_MATCH"
    else:
        source = "DRIFT"
        blockers.append("SOURCE_DRIFT")

    stores = []
    healthy = True
    for origin in ORIGINS:
        okay, reasons, info = _store_check(samples[origin].get("storage"))
        healthy = healthy and okay
        blockers.extend(reasons)
        stores.append(info)
    if (stores[0]["epoch"] != stores[1]["epoch"]
            or stores[0]["sequence"] != stores[1]["sequence"]):
        healthy = False
        blockers.append("STORAGE_ORIGINS_DISAGREE")
    if not healthy:
        blockers.append("STATE_PRESERVATION_UNQUALIFIED")
    service = samples[ORIGINS[0]].get("health") or {}
    native = service.get("operational_readiness")
    if type(native) is not dict:
        native = {}
    frontier_ready = (service.get("status") == "ok"
                      and native.get("ready") is True
                      and native.get("status") == "READY")
    if not frontier_ready:
        blockers.append("FRONTIER_NOT_READY_OR_UNKNOWN")

    # Neither GitHub/HF declarations nor unsigned transport samples grant authority.
    blockers.append("INDEPENDENT_EXECUTION_PROOF_NOT_VERIFIED")
    match = source == "DECLARATIONS_MATCH" and healthy
    report = {
        "schema": SCHEMA, "scope": "UNSIGNED_READ_ONLY_OBSERVATION",
        "started_at": started_at, "completed_at": clock(),
        "main": {"before": before, "after": after, "repository": REPOSITORY},
        "source": {"state": source, "declared_revisions": declared,
                   "evidence_class": "DECLARED_NOT_BYTE_VERIFIED"},
        "storage": {"state": "HEALTHY_REPORTED" if healthy else "UNQUALIFIED",
                    "origins": stores},
        "frontier": {"state": "READY_REPORTED" if frontier_ready else "NOT_READY_OR_UNKNOWN",
                     "native_state": native.get("status") if type(native.get("status")) is str
                                     else "UNKNOWN"},
        "observational_convergence": match,
        "production_qualified": False, "can_deploy": False,
        "gate_vector": [
            {"gate": "SOURCE_DECLARATIONS", "observed": source == "DECLARATIONS_MATCH",
             "proof": "DECLARATIONS_ONLY"},
            {"gate": "STATE_PRESERVATION", "observed": healthy,
             "proof": "UNSIGNED_HTTP_OBSERVATION"},
            {"gate": "FRONTIER_READINESS", "observed": frontier_ready,
             "proof": "SERVICE_SELF_REPORT"},
            {"gate": "EXECUTION_AUTHORITY", "observed": False,
             "proof": "NOT_EVALUATED"},
        ],
        "blocker_codes": sorted(set(blockers)),
        "evidence": evidence,
        "boundaries": {
            "source_byte_binding": "NOT_VERIFIED",
            "cryptographic_signatures": "NOT_VERIFIED",
            "runtime_execution": "NOT_EVALUATED",
            "restore_drill": "NOT_EVALUATED",
            "monetization_settlement": "NOT_EVALUATED",
        },
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=False).encode("utf-8")
    report["observation_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report

"""SZL Command Center — FastAPI backend.

Serves the static mission-control frontend at / and two JSON endpoints:

    GET /api/estate     one tree for all panels (github, huggingface,
                        cloudflare, dns, receipts) + estate truth summary
    GET /api/verticals  the five verticals with repos, health, open issues
    GET /api/health     liveness

Every collector returns truth-state envelopes; a collector failure never
breaks the page — the panel shows UNAVAILABLE with the reason. Responses
are cached 60s in-memory.

Run:  uvicorn backend.main:app --port 8000
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import convergence, verticals as verticals_mod
from .cache import ResponseCache
from .collectors import cloudflare, dns, github, huggingface, receipts
from .collectors.base import roll_up, utc_now

from .ontology import project as project_ontology
from .inference import router as inference_router

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
CACHE_TTL = 60

app = FastAPI(
    title="SZL Command Center",
    description="Governed business observability across the SZL estate. Nothing renders without a truth state.",
    version="1.0.0",
)

_response_cache = ResponseCache(CACHE_TTL)


def _cached(key: str, producer):
    return _response_cache.get(key, producer)


def _estate() -> dict:
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            "github": pool.submit(github.collect),
            "huggingface": pool.submit(huggingface.collect),
            "cloudflare": pool.submit(cloudflare.collect),
            "dns": pool.submit(dns.collect),
            "receipts": pool.submit(receipts.collect),
        }
        collectors = {name: fut.result() for name, fut in futures.items()}

    states = {name: env["truth_state"] for name, env in collectors.items()}
    verified_count = sum(1 for s in states.values() if s == "VERIFIED")
    return {
        "generated_at": utc_now(),
        "cache_ttl_seconds": CACHE_TTL,
        "summary": {
            "panels_total": len(states),
            "panels_verified": verified_count,
            "verified_ratio": verified_count / len(states) if states else 0,
            "estate_state": roll_up(list(states.values())),
            "states": states,
        },
        "collectors": collectors,
    }


def _snapshot(name: str) -> dict | None:
    """Load dated historical context; never substitute it for live evidence."""
    path = os.path.join(os.path.dirname(__file__), "snapshot", f"{name}.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["_served_from"] = "baked-snapshot"
        return data
    except (OSError, json.JSONDecodeError):
        return None


def _live_or_snapshot(name: str, producer) -> JSONResponse:
    payload = producer()
    collectors = payload.get("collectors") if isinstance(payload, dict) else None
    if collectors is not None:
        github_env = collectors.get("github") or {}
        gh_state = github_env.get("truth_state")
        if gh_state != "VERIFIED":
            snap = _snapshot(name)
            if snap is not None:
                # Keep current failures, timestamps and other collectors intact.
                # Do not mutate the shared cached payload.
                payload = {**payload, "_historical_snapshot": snap}
    return JSONResponse(payload)


@app.get("/api/estate")
def api_estate() -> JSONResponse:
    return _live_or_snapshot("estate", lambda: _cached("estate", _estate))


@app.get("/api/verticals")
def api_verticals() -> JSONResponse:
    payload = _cached("verticals", verticals_mod.collect)
    snap = _snapshot("verticals")
    verticals = payload.get("verticals") if isinstance(payload, dict) else None
    if snap is not None and isinstance(verticals, list) and verticals and all(
        isinstance(vertical, dict)
        and vertical.get("truth_state") in ("UNAVAILABLE", "UNKNOWN")
        for vertical in verticals
    ):
        payload = {**payload, "_historical_snapshot": snap}
    return JSONResponse(payload)


@app.get("/api/convergence")
def api_convergence() -> JSONResponse:
    """Read-only main/runtime/lease witness, not deployment approval."""
    return JSONResponse(_cached("convergence", convergence.collect))


@app.get("/api/ontology")
def api_ontology() -> JSONResponse:
    """Disabled until admission; no independent data sources or action rights."""
    if os.environ.get("SZL_ONTOLOGY_READONLY_ENABLED") != "1":
        return JSONResponse(
            {"status": "UNAVAILABLE", "reason_code": "FEATURE_NOT_ADMITTED"},
            status_code=503,
            headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
        )
    return JSONResponse(
        project_ontology(_cached("estate", _estate)),
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
    )


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok", "at": utc_now()}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.include_router(inference_router)

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

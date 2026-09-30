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

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import verticals as verticals_mod
from .collectors import cloudflare, dns, github, huggingface, receipts
from .collectors.base import roll_up, utc_now

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
CACHE_TTL = 60

app = FastAPI(
    title="SZL Command Center",
    description="Governed business observability across the SZL estate. Nothing renders without a truth state.",
    version="1.0.0",
)

_cache: dict = {}
_cache_lock = threading.Lock()


def _cached(key: str, producer):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit["at"] < CACHE_TTL:
            return hit["payload"]
    payload = producer()
    with _cache_lock:
        _cache[key] = {"at": now, "payload": payload}
    return payload


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


@app.get("/api/estate")
def api_estate() -> JSONResponse:
    return JSONResponse(_cached("estate", _estate))


@app.get("/api/verticals")
def api_verticals() -> JSONResponse:
    return JSONResponse(_cached("verticals", verticals_mod.collect))


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok", "at": utc_now()}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

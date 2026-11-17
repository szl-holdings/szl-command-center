"""Enforce a distinct, non-privileged public-preview data boundary.

A deployed Docker source-manifest is an immutable mode marker for the
research-preview image. Setting environment variables cannot turn that image
into an unauthenticated private operator console. Sensitive collectors,
cached private results, historic snapshots and imported verifier subprocesses
must not be consulted by these public-view payload builders.
"""
from __future__ import annotations

import os
from pathlib import Path

from .collectors.base import envelope, unavailable, utc_now

DEPLOYED_MANIFEST = Path(__file__).resolve().parent.parent / "source_manifest.json"
MODE_VARIABLE = "SZL_COMMAND_CENTER_MODE"
PUBLIC_MODE = "public_preview"
REASON = "PUBLIC_PREVIEW_PRIVILEGED_COLLECTOR_NOT_ADMITTED"
COLLECTORS = ("github", "huggingface", "cloudflare", "dns", "receipts")


def active() -> bool:
    """Source-marked public images remain public even with env overrides."""
    return DEPLOYED_MANIFEST.is_file() or os.environ.get(MODE_VARIABLE) == PUBLIC_MODE


def estate() -> dict:
    """Return an intentional zero-privilege snapshot, not a failed scan."""
    collectors = {
        name: unavailable("public-preview:" + name, REASON)
        for name in COLLECTORS
    }
    states = {name: "UNAVAILABLE" for name in COLLECTORS}
    return {
        "generated_at": utc_now(),
        "cache_ttl_seconds": 60,
        "scope": PUBLIC_MODE,
        "evidence_policy": "PRIVATE_COLLECTORS_NOT_QUERIED",
        "summary": {
            "panels_total": len(states),
            "panels_verified": 0,
            "verified_ratio": 0.0,
            "estate_state": "UNAVAILABLE",
            "states": states,
        },
        "collectors": collectors,
    }


def verticals() -> dict:
    """Known public repo-name mapping, with no private CI or issue queries."""
    # Import the static public source map, never execute verticals.collect().
    from .verticals import VERTICALS

    rows = []
    for item in VERTICALS:
        repos = [
            {
                "repo": repo,
                "truth_state": "UNAVAILABLE",
                "meta": unavailable("public-preview:github-metadata", REASON),
                "head": None,
                "ci": unavailable("public-preview:github-workflows", REASON),
                "latest_run": None,
                "workflow_rollup": {
                    "ci": "unknown",
                    "protected_merge_readiness": False,
                    "window_complete": False,
                    "failing_workflows": [],
                },
                "open_issues": None,
            }
            for repo in item["repos"]
        ]
        rows.append({
            "id": item["id"],
            "name": item["name"],
            "mission": item["mission"],
            **envelope(
                {"repos": repos, "health": "unknown",
                 "open_issues": None, "last_push": None},
                "UNAVAILABLE", "public-preview:static-vertical-map", REASON,
            ),
        })
    return {
        "generated_at": utc_now(),
        "scope": PUBLIC_MODE,
        "issues_scan": unavailable("public-preview:github-issues", REASON),
        "verticals": rows,
    }

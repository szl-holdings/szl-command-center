"""Hugging Face collector — HTTPS against api.huggingface.co.

Auth comes from the environment at runtime (HF_TOKEN-style variables).
NEVER hardcode a token. If no token is present in the environment, the
panel returns UNAVAILABLE with that exact reason (CANON Law 1).
"""
from __future__ import annotations

import os

import requests

from .base import clip, envelope, unavailable, verified, exc_kind

ORG = "szlholdings"
API = "https://api.huggingface.co"
TIMEOUT = 15
TOKEN_ENV_VARS = (
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "HUGGINGFACE_HUB_TOKEN",
    "HUGGINGFACE_TOKEN",
    "HF_API_TOKEN",
)


def _token() -> str | None:
    for name in TOKEN_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _count(path: str, token: str) -> int:
    resp = requests.get(
        f"{API}{path}",
        params={"author": ORG, "limit": 1000},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return len(resp.json())


def collect() -> dict:
    ref = f"{API}/api/spaces?author={ORG} (+/api/models)"
    token = _token()
    if not token:
        return unavailable(
            ref,
            "no HF token in environment; set one of "
            + ", ".join(TOKEN_ENV_VARS)
            + " — UNAVAILABLE per Zero-Bandaid Law, never a guess",
        )
    try:
        spaces = _count("/api/spaces", token)
        models = _count("/api/models", token)
        datasets = _count("/api/datasets", token)
        return verified(
            {
                "org": ORG,
                "spaces": spaces,
                "models": models,
                "datasets": datasets,
            },
            ref,
        )
    except Exception as exc:  # noqa: BLE001
        return unavailable(ref, exc_kind(exc))

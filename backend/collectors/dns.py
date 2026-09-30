"""DNS collector — subprocess `dig` against public resolvers.

Public data, no token required. DS records at the parent prove the
DNSSEC chain of trust; their absence means unsigned (UNKNOWN), and a
failed dig means UNAVAILABLE. States are reported, never assumed.
"""
from __future__ import annotations

import shutil
import subprocess

from .base import clip, envelope, roll_up, unavailable, unknown, verified

DOMAINS = ("a-11-oy.com", "a11oy.net")
DIG_TIMEOUT = 10


def _dig(domain: str, rtype: str) -> list:
    out = subprocess.run(
        ["dig", "+short", rtype, domain],
        capture_output=True,
        text=True,
        timeout=DIG_TIMEOUT,
    )
    if out.returncode != 0:
        raise RuntimeError(clip(out.stderr.strip() or f"dig exit {out.returncode}"))
    return sorted(line.strip() for line in out.stdout.splitlines() if line.strip())


def _domain(domain: str) -> dict:
    ref = f"dig +short DS {domain} (+NS)"
    if shutil.which("dig") is None:
        return unavailable(ref, "dig not found on PATH")
    try:
        ds = _dig(domain, "DS")
        ns = _dig(domain, "NS")
        dnssec = "SECURE" if ds else "UNSIGNED"
        value = {"domain": domain, "dnssec": dnssec, "ds_records": ds, "ns_records": ns}
        if ds:
            return verified(value, ref)
        return unknown(
            value,
            ref,
            f"no DS records at parent for {domain} — zone is unsigned or not yet delegated with DNSSEC",
        )
    except Exception as exc:  # noqa: BLE001
        return unavailable(ref, clip(exc))


def collect() -> dict:
    domains = {name: _domain(name) for name in DOMAINS}
    state = roll_up([d["truth_state"] for d in domains.values()])
    env = envelope(domains, state, "dig +short DS/NS via system resolver")
    if state != "VERIFIED":
        reasons = [
            d.get("reason") for d in domains.values() if d["truth_state"] != "VERIFIED"
        ]
        env["reason"] = "; ".join(r for r in reasons if r)[:200]
    return env

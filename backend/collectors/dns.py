"""DNS collector — subprocess `dig` against the system resolver.

Public data, no token required. Well-formed DS/NS records are observations,
not DNSSEC chain validation. Empty answers also leave DNSSEC UNKNOWN.
Failed commands and malformed or unsupported answers are UNAVAILABLE.
"""
from __future__ import annotations

import re
import shutil
import subprocess

from .base import clip, envelope, roll_up, unavailable, unknown

DOMAINS = ("a-11-oy.com", "a11oy.net")
DIG_TIMEOUT = 10
# Hex lengths for the supported DS digests: RFC 4034 §5.1.4,
# RFC 4509 §2.1 and RFC 6605 §2. This is format validation only.
DS_DIGEST_HEX_LENGTHS = {1: 40, 2: 64, 4: 96}


def _valid_record(record: str, rtype: str) -> bool:
    if rtype == "DS":
        fields = record.split()
        if len(fields) != 4 or not all(re.fullmatch(r"[0-9]+", x) for x in fields[:3]):
            return False
        key_tag, algorithm, digest_type = map(int, fields[:3])
        return (
            0 <= key_tag <= 65535
            and 1 <= algorithm <= 255
            and digest_type in DS_DIGEST_HEX_LENGTHS
            and len(fields[3]) == DS_DIGEST_HEX_LENGTHS[digest_type]
            and re.fullmatch(r"[0-9a-fA-F]+", fields[3]) is not None
        )
    if rtype == "NS":
        return len(record) <= 254 and re.fullmatch(
            r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+", record
        ) is not None
    return False


def _dig(domain: str, rtype: str) -> list:
    out = subprocess.run(
        ["dig", "+short", rtype, domain],
        capture_output=True,
        text=True,
        timeout=DIG_TIMEOUT,
    )
    if out.returncode != 0:
        raise RuntimeError(clip(out.stderr.strip() or f"dig exit {out.returncode}"))
    records = sorted(line.strip() for line in out.stdout.splitlines() if line.strip())
    if any(not _valid_record(record, rtype) for record in records):
        raise RuntimeError(f"malformed or unsupported {rtype} response from dig")
    return records


def _domain(domain: str) -> dict:
    ref = f"dig +short DS {domain} (+NS)"
    if shutil.which("dig") is None:
        return unavailable(ref, "dig not found on PATH")
    try:
        ds = _dig(domain, "DS")
        ns = _dig(domain, "NS")
        value = {"domain": domain, "dnssec": "UNKNOWN", "ds_records": ds, "ns_records": ns}
        return unknown(
            value,
            ref,
            "DS records observed, but DNSSEC chain not validated"
            if ds else "no DS records observed; DNSSEC chain not validated",
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

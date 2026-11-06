"""Receipts collector — the payload 05 self-audit bundle, verified live.

The collector does not trust the bundle's own prose. It executes the
stdlib reference verifier (payloads/05-verifier/a11oy_verify.py) against
the bundle and reports the verdict the verifier actually returns. Per
CANON Law 4, missing evidence yields INCOMPLETE — never PASS. That
verdict is the demo.

If the bundle or verifier is absent, the panel is UNAVAILABLE with the
path that was checked.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess

from .base import envelope, failure_reason, roll_up, unavailable, unknown, verified

PAYLOADS = "/home/user/workspace/payloads"
BUNDLE = os.path.join(PAYLOADS, "05-verifier", "scratch", "self_audit_bundle.json")
VERIFIER = os.path.join(PAYLOADS, "05-verifier", "a11oy_verify.py")
MASTER = os.path.join(PAYLOADS, "01-master")
VERIFY_TIMEOUT = 45

CHECK_LINE = re.compile(r"^\[(PASS|INCOMPLETE|FAIL|UNVERIFIED[A-Z_]*)\s*\]\s+(.+)$")
FINAL_LINE = re.compile(r"^FINAL:\s*(PASS|INCOMPLETE|FAIL)\s*$")
FINAL_EXIT_CODES = {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}


def _run_verifier() -> dict:
    ref = f"python3 {VERIFIER} {BUNDLE}"
    if not os.path.exists(VERIFIER):
        return unavailable(ref, f"reference verifier not found at {VERIFIER}")
    if not os.path.exists(BUNDLE):
        return unavailable(ref, f"self-audit bundle not found at {BUNDLE}")
    try:
        proc = subprocess.run(
            ["python3", VERIFIER, BUNDLE],
            capture_output=True,
            text=True,
            timeout=VERIFY_TIMEOUT,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        checks = []
        verdicts = []
        for line in output.splitlines():
            m = CHECK_LINE.match(line.strip())
            if m:
                name, _, detail = m.group(2).partition(":")
                checks.append(
                    {"state": m.group(1), "check": name.strip(), "detail": detail.strip()[:160]}
                )
                continue
            f = FINAL_LINE.match(line.strip())
            if f:
                verdicts.append(f.group(1))
        if not verdicts:
            return unknown(
                {"checks": checks},
                ref,
                "verifier produced no FINAL verdict line — output unrecognized",
            )
        if len(verdicts) != 1:
            return unknown(
                {
                    "checks": checks,
                    "reported_verdicts": verdicts,
                    "returncode": proc.returncode,
                },
                ref,
                "verifier produced multiple FINAL verdict lines — output ambiguous",
            )
        verdict = verdicts[0]
        expected_returncode = FINAL_EXIT_CODES[verdict]
        if proc.returncode != expected_returncode:
            return unknown(
                {
                    "checks": checks,
                    "reported_verdict": verdict,
                    "returncode": proc.returncode,
                    "expected_returncode": expected_returncode,
                },
                ref,
                (
                    f"verifier FINAL {verdict} disagrees with exit status "
                    f"{proc.returncode}; expected {expected_returncode}"
                ),
            )
        return verified({"verdict": verdict, "checks": checks}, ref)
    except Exception as exc:  # noqa: BLE001
        return unavailable(ref, failure_reason(exc))


def _bundle_facts() -> dict:
    ref = BUNDLE
    if not os.path.exists(BUNDLE):
        return unavailable(ref, f"self-audit bundle not found at {BUNDLE}")
    try:
        with open(BUNDLE, "r", encoding="utf-8") as fh:
            bundle = json.load(fh)
        receipt = (bundle.get("receipts") or [{}])[0]
        payload = receipt.get("payload") or {}
        decision = payload.get("decision") or {}
        predicate = payload.get("predicate") or {}
        return verified(
            {
                "bundle_id": bundle.get("bundle_id"),
                "bundle_type": bundle.get("bundle_type"),
                "created_at": bundle.get("created_at"),
                "receipt_id": payload.get("receipt_id"),
                "decision": decision.get("decision"),
                "side_effect_class": decision.get("effective_side_effect_class"),
                "evidence_obligations": decision.get("evidence_obligations") or [],
                "retention_days": payload.get("retention_days"),
                "action_type": predicate.get("action_type"),
                "completeness": predicate.get("completeness"),
                "chain_sequence": (receipt.get("chain") or {}).get("sequence"),
                "verifier_note": bundle.get("verifier_note"),
            },
            ref,
        )
    except Exception as exc:  # noqa: BLE001
        return unavailable(ref, failure_reason(exc))


def _master_demo_state() -> dict:
    ref = f"{MASTER} (demo state)"
    if not os.path.isdir(MASTER):
        return unavailable(ref, f"master payload directory not found at {MASTER}")
    patterns = ("**/demo*state*.json", "**/demo_state*.json", "**/state*.json")
    hits: list = []
    for pattern in patterns:
        hits.extend(glob.glob(os.path.join(MASTER, pattern), recursive=True))
    hits = sorted(set(h for h in hits if os.path.isfile(h)))
    if not hits:
        return unavailable(
            ref,
            "no demo state JSON present under payloads/01-master — state absent, reported not blank",
        )
    return verified({"state_files": hits[:10], "count": len(hits)}, ref)


def collect() -> dict:
    run = _run_verifier()
    facts = _bundle_facts()
    master = _master_demo_state()
    state = roll_up(
        [run["truth_state"], facts["truth_state"], master["truth_state"]]
    )
    # The verdict itself is verified by execution even when master demo
    # state is absent; surface the roll-up but keep sub-envelopes legible.
    env = envelope(
        {"verification": run, "bundle": facts, "master_demo_state": master},
        state,
        "payloads/05-verifier (reference verifier + self-audit bundle)",
    )
    if state != "VERIFIED":
        reasons = [
            sub.get("reason")
            for sub in (run, facts, master)
            if sub["truth_state"] != "VERIFIED"
        ]
        env["reason"] = "; ".join(r for r in reasons if r)[:240]
    return env

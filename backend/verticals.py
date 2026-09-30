"""The five SZL verticals and their repo membership.

Mapping derived from payloads/17-verticals/repo_census.txt descriptions
(100-repo estate map). Only live (non-archived) repos are tracked here.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .collectors import github
from .collectors.base import envelope, roll_up, utc_now

VERTICALS = [
    {
        "id": "governance",
        "name": "Governance",
        "mission": "Signed receipts, policy gates, proof of governed action.",
        "repos": [
            "a11oy",
            "governance-as-code",
            "szl-receipt",
            "governed-receipt-spec",
            "szl-gov",
            "evidence-doctrine",
        ],
    },
    {
        "id": "counter-uas",
        "name": "Counter-UAS",
        "mission": "Tracks, fusion, ROE — DSSE receipts per interdiction.",
        "repos": ["killinchu", "szl-substrate", "khipu-sda-core", "khipu-consensus"],
    },
    {
        "id": "insurance",
        "name": "Insurance",
        "mission": "Evidence-bound underwriting and public trust surfaces.",
        "repos": ["szl-real-estate", "szl-trust"],
    },
    {
        "id": "quant",
        "name": "Quant",
        "mission": "Doctrine-governed signals with a second witnessing vantage.",
        "repos": ["szl-quant", "szl-quant-witness"],
    },
    {
        "id": "energy-metered-inference",
        "name": "Energy-Metered Inference",
        "mission": "Measured joules per governed inference — or honest UNAVAILABLE.",
        "repos": ["szl-energy-attest", "szl-command-lab", "szl-gpu-bridge"],
    },
]


def _repo_state(repo: str, issues_by_repo: dict | None) -> dict:
    """One repo row: metadata envelope + latest-CI envelope + issue count."""
    meta = github.repo_meta(repo)
    runs = github.ci_runs(repo, limit=3)
    latest = None
    if runs["truth_state"] == "VERIFIED" and runs["value"]:
        latest = runs["value"][0]
    issues = None
    if issues_by_repo is not None:
        issues = issues_by_repo.get(repo, 0)
    states = [meta["truth_state"], runs["truth_state"]]
    return {
        "repo": repo,
        "truth_state": roll_up(states),
        "meta": meta,
        "ci": runs,
        "latest_run": latest,
        "open_issues": issues,
    }


def _health(repos: list) -> str:
    """Vertical health from latest CI conclusions.

    ok       — every repo with runs is green, none failing.
    degraded — at least one latest run failed.
    unknown  — no CI conclusions observed at all.
    """
    conclusions = [
        (r["latest_run"] or {}).get("conclusion")
        for r in repos
        if r.get("latest_run")
    ]
    if not conclusions:
        return "unknown"
    if any(c == "failure" for c in conclusions):
        return "degraded"
    if all(c == "success" for c in conclusions):
        return "ok"
    return "unknown"


def collect() -> dict:
    """/api/verticals payload — five verticals, repos, health, open issues."""
    issues_env = github.open_issues_by_repo()
    issues_by_repo = None
    if issues_env["truth_state"] == "VERIFIED":
        issues_by_repo = (issues_env["value"] or {}).get("by_repo") or {}

    all_repos = sorted({repo for v in VERTICALS for repo in v["repos"]})
    with ThreadPoolExecutor(max_workers=8) as pool:
        repo_states = dict(
            zip(all_repos, pool.map(lambda r: _repo_state(r, issues_by_repo), all_repos))
        )

    verticals = []
    for v in VERTICALS:
        repos = [repo_states[r] for r in v["repos"]]
        state = roll_up([r["truth_state"] for r in repos])
        open_issues = (
            sum(r["open_issues"] or 0 for r in repos)
            if issues_by_repo is not None
            else None
        )
        last_push = max(
            (
                (r["meta"]["value"] or {}).get("pushed_at")
                for r in repos
                if r["meta"]["truth_state"] == "VERIFIED"
                and (r["meta"]["value"] or {}).get("pushed_at")
            ),
            default=None,
        )
        env = envelope(
            {
                "repos": repos,
                "health": _health(repos),
                "open_issues": open_issues,
                "last_push": last_push,
            },
            state,
            "gh api /repos + gh run list per repo; gh search issues org-wide",
        )
        if state != "VERIFIED":
            reasons = {
                r["meta"].get("reason") for r in repos if r["meta"].get("reason")
            } | {r["ci"].get("reason") for r in repos if r["ci"].get("reason")}
            env["reason"] = "; ".join(sorted(reasons))[:240]
        verticals.append(
            {
                "id": v["id"],
                "name": v["name"],
                "mission": v["mission"],
                **env,
            }
        )

    return {
        "generated_at": utc_now(),
        "issues_scan": issues_env,
        "verticals": verticals,
    }

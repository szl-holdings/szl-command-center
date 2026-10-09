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
    """One repo row: metadata, one push-window page, and a per-workflow roll-up."""
    meta = github.repo_meta(repo)
    meta_value = meta.get("value") or {}
    archived = meta["truth_state"] == "VERIFIED" and bool(meta_value.get("archived"))
    branch = meta_value.get("default_branch") or "main"
    head = github.repo_head(repo, branch) if not archived else None
    current_head = None
    if head and head["truth_state"] == "VERIFIED":
        current_head = (head.get("value") or {}).get("sha")
    observed = github.workflow_observation(
        repo,
        branch,
        current_head=current_head,
        archived=archived,
    )
    observed_value = observed.get("value") or {}
    runs = observed_value.get("runs") or []
    latest = runs[0] if observed["truth_state"] == "VERIFIED" and runs else None
    rollup = observed_value.get("rollup") or github.summarize_workflow_window(
        [], archived=archived
    )
    issues = None
    if issues_by_repo is not None:
        issues = issues_by_repo.get(repo, 0)
    states = [meta["truth_state"], observed["truth_state"]]
    if head is not None:
        states.append(head["truth_state"])
    return {
        "repo": repo,
        "truth_state": roll_up(states),
        "meta": meta,
        "head": head,
        "ci": observed,
        "latest_run": latest,
        "workflow_rollup": rollup,
        "open_issues": issues,
    }


def _health(repos: list) -> str:
    """Health from the latest observed run of each workflow.

    A newer green run of one workflow does not hide another workflow's
    failure. An incomplete collection window is not ok. ok is not
    protected-merge readiness.
    """
    states = []
    incomplete = False
    for repo in repos:
        meta_value = ((repo.get("meta") or {}).get("value") or {})
        rollup = repo.get("workflow_rollup") or {}
        if meta_value.get("archived") is True or rollup.get("ci") == "archived":
            states.append("archived")
            continue
        if rollup.get("window_complete") is not True:
            incomplete = True
        head_env = repo.get("head")
        if isinstance(head_env, dict) and head_env.get("truth_state") != "VERIFIED":
            incomplete = True
        states.append(rollup.get("ci") or "unknown")
    active = [state for state in states if state != "archived"]
    if states and not active:
        return "archived"
    if any(state == "failure" for state in active):
        return "degraded"
    if incomplete or not active or any(state != "success" for state in active):
        return "unknown"
    return "ok"


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
            "gh api repos, commits, and one page of default-branch push runs; "
            "latest run per workflow; not protected-merge readiness",
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

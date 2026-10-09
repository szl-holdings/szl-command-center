"""GitHub collector — shells out to the `gh` CLI.

Auth comes from the environment at runtime (GH_TOKEN / `gh auth login`).
No token is ever hardcoded. If `gh` is missing or unauthenticated, every
envelope degrades to UNAVAILABLE with the reason — an audited state,
never a blank (CANON Law 1).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.parse

from .base import clip, envelope, roll_up, unavailable, verified

ORG = "szl-holdings"
FLAGSHIP = "a11oy"
GH_TIMEOUT = 25
# Same observation width as szl-org-health census/github.py at
# fb81f4082827312d5298b1ddcd24dd40ea426457. It is one page of recent
# default-branch push runs, not every required check.
RUN_WINDOW = 100
FAILURE_CONCLUSIONS = {
    "action_required",
    "cancelled",
    "failure",
    "stale",
    "startup_failure",
    "timed_out",
}
GREEN_CONCLUSIONS = {"neutral", "skipped", "success"}
PENDING_STATUSES = {"in_progress", "pending", "queued", "requested", "waiting"}
CI_SCOPE = "latest-per-workflow-within-recent-default-branch-push-window"


def _gh(args: list, timeout: int = GH_TIMEOUT) -> str:
    """Run a gh command, returning stdout. Raises RuntimeError on any failure."""
    if shutil.which("gh") is None:
        raise RuntimeError("gh CLI not found on PATH")
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise RuntimeError(clip(detail, 160))
    return proc.stdout


def _workflow_key(run: dict) -> str:
    return str(
        run.get("workflow_id")
        or run.get("workflowName")
        or run.get("name")
        or run.get("id")
        or "unknown"
    )


def _workflow_stamp(run: dict) -> str:
    return str(
        run.get("created_at")
        or run.get("run_started_at")
        or run.get("updatedAt")
        or ""
    )


def _workflow_name(run: dict, key: str) -> str:
    return str(run.get("name") or run.get("workflowName") or key)


def _same_head(run_sha: str, current_head: str) -> bool:
    left = (run_sha or "").strip().lower()
    right = (current_head or "").strip().lower()
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 7 and longer.startswith(shorter)


def aggregate_workflow_runs(runs: list) -> dict:
    """Latest observed run per workflow.

    Adapted from szl-org-health census/github.py aggregate_workflow_runs at
    fb81f4082827312d5298b1ddcd24dd40ea426457. An unrelated newer green run
    does not hide another workflow's older failure. This is not
    protected-merge readiness.
    """
    latest: dict = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        key = _workflow_key(run)
        stamp = _workflow_stamp(run)
        current = latest.get(key)
        if current is None or stamp > _workflow_stamp(current):
            latest[key] = run

    if not latest:
        return {
            "ci": "unknown",
            "workflow_count": 0,
            "failing_workflows": [],
            "pending_workflows": [],
            "unknown_workflows": [],
        }

    failing: list = []
    pending: list = []
    unknown: list = []
    for key, run in latest.items():
        name = _workflow_name(run, key)
        status = run.get("status")
        conclusion = run.get("conclusion")
        if status == "completed" and conclusion in FAILURE_CONCLUSIONS:
            failing.append(name)
        elif status == "completed" and conclusion in GREEN_CONCLUSIONS:
            continue
        elif status in PENDING_STATUSES and conclusion is None:
            pending.append(name)
        else:
            unknown.append(name)
    failing.sort()
    pending.sort()
    unknown.sort()
    ci = (
        "failure"
        if failing
        else "unknown"
        if unknown
        else "pending"
        if pending
        else "success"
    )
    return {
        "ci": ci,
        "workflow_count": len(latest),
        "failing_workflows": failing,
        "pending_workflows": pending,
        "unknown_workflows": unknown,
    }


def summarize_workflow_window(
    runs: list,
    *,
    current_head: str | None = None,
    total_count: int | None = None,
    archived: bool = False,
) -> dict:
    """Add archive, head, and collection-window facts around the reducer.

    ``protected_merge_readiness`` stays false. A full green window is still
    only the recent default-branch push page.
    """
    observed = [run for run in runs if isinstance(run, dict)]
    window_complete = isinstance(total_count, int) and total_count == len(observed)
    base = {
        "protected_merge_readiness": False,
        "ci_scope": "archived" if archived else CI_SCOPE,
        "run_window_observed": 0 if archived else len(observed),
        "default_branch_push_runs_total": None if archived else total_count,
        "window_complete": False if archived else window_complete,
        "other_head_count": 0,
        "missing_workflow_identity": False,
    }
    if archived:
        base.update(
            {
                "ci": "archived",
                "workflow_count": 0,
                "failing_workflows": [],
                "pending_workflows": [],
                "unknown_workflows": [],
            }
        )
        return base

    current_runs = []
    other_head = 0
    missing_identity = False
    for run in observed:
        if not (run.get("workflow_id") or run.get("workflowName") or run.get("name") or run.get("id")):
            missing_identity = True
        sha = str(run.get("head_sha") or run.get("headSha") or "")
        if current_head and not _same_head(sha, current_head):
            other_head += 1
            continue
        current_runs.append(run)
    summary = aggregate_workflow_runs(current_runs)
    summary.update(base)
    summary["other_head_count"] = other_head
    summary["missing_workflow_identity"] = missing_identity
    if missing_identity and summary["ci"] == "success":
        summary["ci"] = "unknown"
        if "unknown" not in summary["unknown_workflows"]:
            summary["unknown_workflows"] = sorted([*summary["unknown_workflows"], "unknown"])
    return summary


def _normalize_actions_run(run: dict) -> dict:
    sha = run.get("head_sha") or ""
    return {
        "conclusion": run.get("conclusion"),
        "workflowName": run.get("name"),
        "name": run.get("name"),
        "workflow_id": run.get("workflow_id"),
        "id": run.get("id"),
        "updatedAt": run.get("updated_at"),
        "created_at": run.get("created_at"),
        "run_started_at": run.get("run_started_at"),
        "status": run.get("status"),
        "head_sha": sha,
        "headSha": sha,
        "url": run.get("html_url"),
    }


def workflow_observation(
    repo: str,
    branch: str = "main",
    *,
    current_head: str | None = None,
    archived: bool = False,
    limit: int = RUN_WINDOW,
) -> dict:
    """One page of default-branch push runs, reduced per workflow.

    Incomplete pagination stays incomplete. This does not walk further pages
    and does not decide protected-merge readiness.
    """
    if archived:
        ref = f"archived repo {ORG}/{repo}"
        return verified(
            {
                "runs": [],
                "rollup": summarize_workflow_window([], archived=True),
                "total_count": None,
            },
            ref,
        )
    quoted_repo = urllib.parse.quote(repo)
    quoted_branch = urllib.parse.quote(branch)
    path = (
        f"/repos/{ORG}/{quoted_repo}/actions/runs"
        f"?branch={quoted_branch}&event=push&per_page={int(limit)}"
    )
    ref = f"gh api {path}"
    try:
        data = json.loads(_gh(["api", path], timeout=40))
        raw_runs = data.get("workflow_runs") if isinstance(data, dict) else None
        if not isinstance(raw_runs, list):
            return unavailable(ref, "workflow runs payload did not include a list")
        runs = [_normalize_actions_run(run) for run in raw_runs if isinstance(run, dict)]
        total = data.get("total_count")
        if isinstance(total, bool) or not isinstance(total, int):
            total = None
        return verified(
            {
                "runs": runs,
                "rollup": summarize_workflow_window(
                    runs, current_head=current_head, total_count=total
                ),
                "total_count": total,
            },
            ref,
        )
    except Exception as exc:  # noqa: BLE001 — failure must never break the page
        return unavailable(ref, clip(exc))


def ci_runs(repo: str, limit: int = 5) -> dict:
    """Latest workflow runs for one repo."""
    ref = f"gh run list --repo {ORG}/{repo} --limit {limit}"
    try:
        out = _gh(
            [
                "run", "list",
                "--repo", f"{ORG}/{repo}",
                "--limit", str(limit),
                "--json", "conclusion,workflowName,updatedAt,status,headSha,url",
            ]
        )
        runs = json.loads(out)
        for run in runs:
            sha = run.pop("headSha", "") or ""
            run["head_sha"] = sha[:7] if sha else None
        return verified(runs, ref)
    except Exception as exc:  # noqa: BLE001 — failure must never break the page
        return unavailable(ref, clip(exc))


def open_issues_by_repo(limit: int = 500) -> dict:
    """Org-wide open issue counts, bucketed per repository in one query."""
    ref = f"gh search issues --owner {ORG} --state open"
    try:
        out = _gh(
            [
                "search", "issues",
                "--owner", ORG,
                "--state", "open",
                "--limit", str(limit),
                "--json", "number,repository",
            ],
            timeout=40,
        )
        issues = json.loads(out)
        by_repo: dict = {}
        for issue in issues:
            name = (issue.get("repository") or {}).get("nameWithOwner", "")
            short = name.split("/")[-1] if name else "?"
            by_repo[short] = by_repo.get(short, 0) + 1
        truncated = len(issues) >= limit
        return verified(
            {"total": len(issues), "by_repo": by_repo, "truncated": truncated},
            ref,
        )
    except Exception as exc:  # noqa: BLE001
        return unavailable(ref, clip(exc))


def repo_meta(repo: str) -> dict:
    """Repository metadata: last push, archival, visibility, description."""
    ref = f"gh api /repos/{ORG}/{repo}"
    try:
        out = _gh(["api", f"/repos/{ORG}/{repo}"], timeout=20)
        data = json.loads(out)
        return verified(
            {
                "name": data.get("name", repo),
                "pushed_at": data.get("pushed_at"),
                "archived": bool(data.get("archived")),
                "private": bool(data.get("private")),
                "description": data.get("description"),
                "default_branch": data.get("default_branch", "main"),
                "url": data.get("html_url", f"https://github.com/{ORG}/{repo}"),
            },
            ref,
        )
    except Exception as exc:  # noqa: BLE001
        return unavailable(ref, clip(exc))


def repo_head(repo: str, branch: str = "main") -> dict:
    """HEAD commit of the default branch (deployment-drift anchor, Law 9)."""
    ref = f"gh api /repos/{ORG}/{repo}/commits/{branch}"
    try:
        out = _gh(["api", f"/repos/{ORG}/{repo}/commits/{branch}"], timeout=20)
        data = json.loads(out)
        commit = data.get("commit") or {}
        return verified(
            {
                "sha": (data.get("sha") or "")[:12],
                "message": clip((commit.get("message") or "").splitlines()[0], 120),
                "committed_at": ((commit.get("committer") or {}).get("date")),
            },
            ref,
        )
    except Exception as exc:  # noqa: BLE001
        return unavailable(ref, clip(exc))


def collect() -> dict:
    """Top-level GitHub panel envelope for /api/estate."""
    issues = open_issues_by_repo()
    runs = ci_runs(FLAGSHIP, limit=5)
    head = repo_head(FLAGSHIP)
    state = roll_up(
        [issues["truth_state"], runs["truth_state"], head["truth_state"]]
    )
    env = envelope(
        {
            "org": ORG,
            "open_issues": issues,
            "flagship": {"repo": FLAGSHIP, "runs": runs, "head": head},
        },
        state,
        "gh CLI (org search + run list + commits API)",
    )
    if state != "VERIFIED":
        reasons = [
            sub.get("reason")
            for sub in (issues, runs, head)
            if sub["truth_state"] != "VERIFIED"
        ]
        env["reason"] = "; ".join(r for r in reasons if r)[:200]
    return env

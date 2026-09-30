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

from .base import clip, envelope, roll_up, unavailable, verified

ORG = "szl-holdings"
FLAGSHIP = "a11oy"
GH_TIMEOUT = 25


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

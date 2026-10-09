"""Offline fixtures for the latest-observed-per-workflow reducer.

The donor is szl-org-health census/github.py aggregate_workflow_runs at
fb81f4082827312d5298b1ddcd24dd40ea426457. These fixtures do not call GitHub.
A green result is not protected-merge readiness.
"""
import unittest
from unittest.mock import patch

from backend.collectors.github import summarize_workflow_window
from backend.verticals import _health, _repo_state


def _run(name, stamp, conclusion, status="completed", head="a" * 40, workflow_id=None):
    return {
        "workflowName": name,
        "name": name,
        "workflow_id": workflow_id if workflow_id is not None else name,
        "created_at": stamp,
        "updatedAt": stamp,
        "status": status,
        "conclusion": conclusion,
        "head_sha": head,
    }


class WorkflowRollupTests(unittest.TestCase):
    def test_newer_green_does_not_hide_an_older_red_workflow(self):
        summary = summarize_workflow_window(
            [
                _run("green-lane", "2026-10-09T16:00:00Z", "success"),
                _run("red-lane", "2026-10-09T15:00:00Z", "failure"),
            ],
            current_head="a" * 40,
            total_count=2,
        )
        self.assertEqual(summary["ci"], "failure")
        self.assertEqual(summary["failing_workflows"], ["red-lane"])
        self.assertFalse(summary["protected_merge_readiness"])
        self.assertEqual(
            summary["ci_scope"],
            "latest-per-workflow-within-recent-default-branch-push-window",
        )

    def test_newer_green_replaces_an_older_red_of_the_same_workflow(self):
        summary = summarize_workflow_window(
            [
                _run("one-lane", "2026-10-09T16:00:00Z", "success"),
                _run("one-lane", "2026-10-09T15:00:00Z", "failure"),
            ],
            total_count=2,
        )
        self.assertEqual(summary["ci"], "success")
        self.assertEqual(summary["failing_workflows"], [])
        self.assertFalse(summary["protected_merge_readiness"])

    def test_empty_results_are_unknown(self):
        summary = summarize_workflow_window([], total_count=0)
        self.assertEqual(summary["ci"], "unknown")
        self.assertEqual(summary["workflow_count"], 0)
        self.assertTrue(summary["window_complete"])
        self.assertEqual(summary["default_branch_push_runs_total"], 0)

    def test_incomplete_pagination_is_not_a_complete_window(self):
        summary = summarize_workflow_window(
            [_run("green-lane", "2026-10-09T16:00:00Z", "success")],
            total_count=140,
        )
        self.assertEqual(summary["ci"], "success")
        self.assertFalse(summary["window_complete"])
        self.assertEqual(summary["run_window_observed"], 1)
        self.assertEqual(summary["default_branch_push_runs_total"], 140)
        self.assertFalse(summary["protected_merge_readiness"])

    def test_changed_head_green_does_not_count_for_the_current_head(self):
        current = "a" * 40
        other = "b" * 40
        summary = summarize_workflow_window(
            [
                _run("green-lane", "2026-10-09T16:00:00Z", "success", head=other),
                _run("red-lane", "2026-10-09T15:00:00Z", "failure", head=current),
            ],
            current_head=current,
            total_count=2,
        )
        self.assertEqual(summary["ci"], "failure")
        self.assertEqual(summary["other_head_count"], 1)
        self.assertEqual(summary["failing_workflows"], ["red-lane"])

    def test_only_another_head_is_not_success(self):
        summary = summarize_workflow_window(
            [_run("green-lane", "2026-10-09T16:00:00Z", "success", head="b" * 40)],
            current_head="a" * 40,
            total_count=1,
        )
        self.assertEqual(summary["ci"], "unknown")
        self.assertEqual(summary["other_head_count"], 1)
        self.assertFalse(summary["protected_merge_readiness"])

    def test_missing_workflow_identity_is_unknown(self):
        summary = summarize_workflow_window(
            [
                {
                    "created_at": "2026-10-09T16:00:00Z",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": "a" * 40,
                }
            ],
            total_count=1,
        )
        self.assertTrue(summary["missing_workflow_identity"])
        self.assertEqual(summary["ci"], "unknown")
        self.assertIn("unknown", summary["unknown_workflows"])

    def test_pending_execution_stays_pending(self):
        summary = summarize_workflow_window(
            [_run("build", "2026-10-09T16:00:00Z", None, status="queued")],
            total_count=1,
        )
        self.assertEqual(summary["ci"], "pending")
        self.assertEqual(summary["pending_workflows"], ["build"])

    def test_archived_repo_does_not_inherit_run_conclusions(self):
        summary = summarize_workflow_window(
            [_run("red-lane", "2026-10-09T16:00:00Z", "failure")],
            archived=True,
            total_count=1,
        )
        self.assertEqual(summary["ci"], "archived")
        self.assertEqual(summary["ci_scope"], "archived")
        self.assertEqual(summary["failing_workflows"], [])
        self.assertFalse(summary["window_complete"])

    def test_health_uses_the_rollup_rather_than_the_newest_green(self):
        repos = [
            {
                "latest_run": {"conclusion": "success", "workflowName": "green-lane"},
                "workflow_rollup": summarize_workflow_window(
                    [
                        _run("green-lane", "2026-10-09T16:00:00Z", "success"),
                        _run("red-lane", "2026-10-09T15:00:00Z", "failure"),
                    ],
                    total_count=2,
                ),
                "meta": {"truth_state": "VERIFIED", "value": {"archived": False}},
            }
        ]
        self.assertEqual(_health(repos), "degraded")

    def test_unverified_head_blocks_ok(self):
        repos = [
            {
                "latest_run": {"conclusion": "success"},
                "head": {"truth_state": "UNAVAILABLE", "reason": "head lookup failed"},
                "workflow_rollup": summarize_workflow_window(
                    [_run("green-lane", "2026-10-09T16:00:00Z", "success")],
                    total_count=1,
                ),
                "meta": {"value": {}},
            }
        ]
        self.assertEqual(repos[0]["workflow_rollup"]["ci"], "success")
        self.assertEqual(_health(repos), "unknown")

    def test_incomplete_green_window_is_not_ok(self):
        repos = [
            {
                "latest_run": {"conclusion": "success"},
                "workflow_rollup": summarize_workflow_window(
                    [_run("green-lane", "2026-10-09T16:00:00Z", "success")],
                    total_count=8,
                ),
                "meta": {"value": {}},
            }
        ]
        self.assertEqual(repos[0]["workflow_rollup"]["ci"], "success")
        self.assertEqual(_health(repos), "unknown")

    def test_repo_state_keeps_the_newest_run_and_the_workflow_failure(self):
        meta = {
            "truth_state": "VERIFIED",
            "value": {"archived": False, "default_branch": "main"},
        }
        head = {"truth_state": "VERIFIED", "value": {"sha": "a" * 12}}
        runs = [
            _run("green-lane", "2026-10-09T16:00:00Z", "success", head="a" * 40),
            _run("red-lane", "2026-10-09T15:00:00Z", "failure", head="a" * 40),
        ]
        observed = {
            "truth_state": "VERIFIED",
            "value": {
                "runs": runs,
                "rollup": summarize_workflow_window(
                    runs, current_head="a" * 12, total_count=2
                ),
            },
        }
        with patch("backend.verticals.github.repo_meta", return_value=meta), patch(
            "backend.verticals.github.repo_head", return_value=head
        ), patch(
            "backend.verticals.github.workflow_observation", return_value=observed
        ):
            row = _repo_state("a11oy", {})
        self.assertEqual(row["latest_run"]["workflowName"], "green-lane")
        self.assertEqual(row["workflow_rollup"]["ci"], "failure")
        self.assertFalse(row["workflow_rollup"]["protected_merge_readiness"])
        self.assertEqual(_health([row]), "degraded")


if __name__ == "__main__":
    unittest.main()

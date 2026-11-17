#!/usr/bin/env python3
"""Publish the exact clean protected-main Docker bundle into its canonical HF Space.

Default mode is read-only preflight. --execute explicitly authorizes one
non-destructive public preview publication with optimistic parent-commit CAS.
No tokens are printed, copied into Docker, or committed to a repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.errors import RepositoryNotFoundError

from build_command_center_space import build_bundle, git_admission, _git

SPACE_ID = "SZLHOLDINGS/szl-command-center"
EXPECTED_REPO = "szl-holdings/szl-command-center"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*, root: Path, execute: bool, receipt_path: Path) -> int:
    root = root.resolve()
    sha = _git(root, "rev-parse", "HEAD")
    selected = git_admission(root, sha)
    report = {
        "schema": "szl.command-center-space-publication/v1",
        "source_repository": EXPECTED_REPO,
        "source_revision": sha,
        "space": SPACE_ID,
        "mode": "EXECUTE" if execute else "PREFLIGHT",
        "published": False,
        "runtime_verified": False,
        "authority": "NONE",
        "signature_verified": False,
        "status": "PREFLIGHT_VERIFIED",
    }
    with tempfile.TemporaryDirectory(prefix="szl-command-center-hf-") as tmp:
        root_out = Path(tmp) / "upload"
        check = build_bundle(root, root_out, sha, selected=selected)
        if check["status"] != "SELF_CONSISTENT":
            raise RuntimeError("BUNDLE_INTEGRITY_NOT_ESTABLISHED")
        report["manifest_sha256"] = check["manifest_sha256"]
        report["listed_files"] = check["listed_files"]
        if execute:
            api = HfApi()
            user = api.whoami()
            if not any(o.get("name") == "SZLHOLDINGS" for o in user.get("orgs", [])):
                raise RuntimeError("ORG_MEMBERSHIP_UNVERIFIED")
            created = False
            try:
                before = api.space_info(SPACE_ID)
                if getattr(before, "private", None) is not False:
                    raise RuntimeError("EXISTING_SPACE_VISIBILITY_NOT_PUBLIC")
                if getattr(before, "sdk", None) != "docker":
                    raise RuntimeError("EXISTING_SPACE_SDK_NOT_DOCKER")
            except RepositoryNotFoundError:
                api.create_repo(
                    SPACE_ID, repo_type="space", space_sdk="docker",
                    private=False, exist_ok=False,
                )
                created = True
                before = api.space_info(SPACE_ID)
            parent = before.sha
            if not isinstance(parent, str) or len(parent) != 40:
                raise RuntimeError("HF_PARENT_REVISION_UNAVAILABLE")
            if _git(root, "ls-remote", "origin", "refs/heads/main").split()[0] != sha:
                raise RuntimeError("GITHUB_MAIN_MOVED_BEFORE_UPLOAD")
            info = api.upload_folder(
                repo_id=SPACE_ID,
                repo_type="space",
                folder_path=root_out,
                path_in_repo="",
                commit_message="publish: command-center GitHub main " + sha,
                parent_commit=parent,
                run_as_future=False,
            )
            revision = getattr(info, "oid", None)
            if not revision or len(revision) != 40:
                raise RuntimeError("HUB_COMMIT_ID_UNAVAILABLE")
            report["published"] = True
            report["created"] = created
            report["hf_revision"] = revision
            # Independent content re-download from immutable Hub commit, not
            # the local upload cache's own source bytes.
            for path in ("source_manifest.json", "Dockerfile",
                         "backend/source_manifest.py", "backend/main.py",
                         "frontend/index.html", "requirements-space.txt"):
                committed = hf_hub_download(
                    repo_id=SPACE_ID, repo_type="space", revision=revision,
                    filename=path, force_download=True,
                )
                if sha_file(Path(committed)) != sha_file(root_out / path):
                    raise RuntimeError("HF_READBACK_MISMATCH")
            report["hub_bytes_verified"] = True
            latest_main = _git(root, "ls-remote", "origin", "refs/heads/main").split()[0]
            report["main_unchanged_after_upload"] = latest_main == sha
            runtime = "UNKNOWN"
            base = "https://szlholdings-szl-command-center.hf.space"
            for _ in range(12):
                try:
                    req = Request(base + "/api/source-manifest",
                                  headers={"Accept": "application/json"},
                                  method="GET")
                    with urlopen(req, timeout=8) as response:
                        body = response.read(32768)
                        data = json.loads(body)
                        if (response.status == 200
                                and data.get("status") == "SELF_CONSISTENT"
                                and data.get("source_revision") == sha
                                and data.get("manifest_sha256") == check["manifest_sha256"]
                                and data.get("execution_authorized") is False):
                            report["runtime_verified"] = True
                            runtime = "SELF_CONSISTENT"
                            break
                        runtime = "SOURCE_OR_HASH_MISMATCH"
                except (OSError, ValueError, URLError):
                    runtime = "RUNTIME_NOT_YET_VERIFIED"
                time.sleep(10)
            report["runtime_state"] = runtime
            report["status"] = (
                "RUNTIME_OBSERVED" if report["runtime_verified"]
                and report["main_unchanged_after_upload"]
                else "PUBLICATION_INCOMPLETE_OR_SUPERSEDED"
            )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if (not execute or (report["runtime_verified"]
                                and report.get("main_unchanged_after_upload"))) else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--execute", action="store_true")
    p.add_argument("--receipt", type=Path, required=True)
    args = p.parse_args()
    try:
        sys.exit(run(root=args.root, execute=args.execute,
                     receipt_path=args.receipt))
    except Exception as exc:
        # Do not print upstream error bodies, URLs or token-bearing tracebacks.
        print(json.dumps({"status": "FAILED_CLOSED",
                          "exception_type": type(exc).__name__}))
        sys.exit(2)

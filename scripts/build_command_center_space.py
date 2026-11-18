#!/usr/bin/env python3
"""Build a minimal HF Docker Space from an admitted GitHub source checkout.

No provider write. The generated manifest checks local bytes, not publisher
identity, signature, trusted hardware, payment, or execution authorization.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.source_manifest import (
    LOCAL_ONLY_SOURCE_FILES, SCHEMA, SOURCE_REPO, file_hash, source_files, verify,
)

README = """---
title: SZL Command Center
emoji: 🧭
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
---

# SZL Command Center — governed operational observability

**Research-preview dashboard, not a production execution controller.**

Canonical source: https://github.com/szl-holdings/szl-command-center

Exact GitHub source revision: `{source_revision}`

This Space is a derived Docker publication. `/api/source-manifest` checks
the self-consistency of shipped application bytes against a SHA-256 manifest.
Matching local bytes do not prove publisher identity, a GitHub signature,
hardware provenance, model evaluation, payment settlement, or action authority.

Operations, provenance and controls: see the canonical GitHub repository.
"""


class BundleError(ValueError):
    pass


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *arguments],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, timeout=25)
    if result.returncode:
        raise BundleError("GIT_PREFLIGHT_FAILED")
    return result.stdout.strip()


def git_admission(root: Path, revision: str) -> set[str]:
    """Allow only a clean checkout at exact remote protected main."""
    if _git(root, "status", "--porcelain"):
        raise BundleError("DIRTY_CHECKOUT")
    if _git(root, "branch", "--show-current") != "main":
        raise BundleError("NON_MAIN_CHECKOUT")
    if _git(root, "rev-parse", "HEAD") != revision:
        raise BundleError("REVISION_MISMATCH")
    remote = _git(root, "remote", "get-url", "origin")
    if remote not in {
        "https://github.com/szl-holdings/szl-command-center.git",
        "git@github.com:szl-holdings/szl-command-center.git",
    }:
        raise BundleError("FOREIGN_ORIGIN")
    live = _git(root, "ls-remote", "origin", "refs/heads/main")
    if not live or live.split()[0] != revision:
        raise BundleError("PROTECTED_MAIN_MOVED_OR_UNAVAILABLE")
    tracked = set(_git(root, "ls-files", "--", "Dockerfile",
                       "requirements-space.txt", "backend", "frontend").splitlines())
    # Source-only Lake operator tooling remains in GitHub for offline testing,
    # but must be intentionally absent from the derived public Docker image.
    names = tracked - LOCAL_ONLY_SOURCE_FILES
    if names != source_files(root, allow_local_only_source=True):
        raise BundleError("UNTRACKED_OR_MISSING_RUNTIME_FILE")
    return names


def build_bundle(root: Path, output: Path, revision: str,
                 *, selected: set[str] | None = None) -> dict:
    root, output = Path(root), Path(output)
    if not isinstance(revision, str) or len(revision) != 40 or any(
        char not in "0123456789abcdef" for char in revision
    ):
        raise BundleError("INVALID_SOURCE_REVISION")
    if output.exists() and any(output.iterdir()):
        raise BundleError("OUTPUT_NOT_EMPTY")
    expected = source_files(root, allow_local_only_source=True)
    if selected is not None and set(selected) != expected:
        raise BundleError("SOURCE_CLOSURE_DRIFT")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for relative in sorted(expected):
        length, digest = file_hash(root, relative)
        rows.append({"path": relative, "bytes": length, "sha256": digest})
        target = output.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root.joinpath(*relative.split("/")), target)
    manifest = {
        "schema": SCHEMA,
        "source_repository": SOURCE_REPO,
        "source_revision": revision,
        "files": rows,
    }
    # The self-check file is intentionally excluded from its own digest.
    (output / "source_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True) + "\n", encoding="utf-8"
    )
    for doc in ("LICENSE", "NOTICE"):
        if (root / doc).is_file():
            shutil.copyfile(root / doc, output / doc)
    (output / "README.md").write_text(README.format(
        source_revision=revision), encoding="utf-8")
    receipt = verify(output)
    if receipt["status"] != "SELF_CONSISTENT" or receipt["listed_files"] != len(rows):
        raise BundleError("INDEPENDENT_BUNDLE_CHECK_FAILED")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-revision", required=True)
    args = parser.parse_args()
    selected = git_admission(args.root, args.expected_revision)
    report = build_bundle(args.root, args.output, args.expected_revision,
                          selected=selected)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

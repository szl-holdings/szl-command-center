"""Local deployment-byte witness; source revision is DECLARED, not signed.

This module checks a manifest generated from an exact Git checkout. It does not
authenticate the publisher, sign a receipt or authorize execution.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

SCHEMA = "szl.command-center-space-source/v1"
RESULT_SCHEMA = "szl.command-center-local-bytes/v1"
SOURCE_REPO = "szl-holdings/szl-command-center"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ALLOWED_SUFFIXES = frozenset({".py", ".json", ".html", ".css", ".js", ".svg"})
FIXED_FILES = frozenset({"Dockerfile", "requirements-space.txt"})
# Explicit source-only modules must NEVER enter the public Docker bundle.
# Do not silently ignore these paths in a deployed bundle: verify() refuses
# their presence even if the manifest omits them.
LOCAL_ONLY_SOURCE_FILES = frozenset({"backend/lake_operator_bridge.py"})
MAX_MANIFEST_BYTES = 256_000
MAX_FILE_BYTES = 2_000_000
MAX_FILES = 1000


class ManifestError(ValueError):
    """A bounded source manifest did not meet its declared contract."""


def source_files(root: Path, *, allow_local_only_source: bool = False) -> set[str]:
    """Enumerate the public runtime payload and deny local operator code.

    The audited source checkout may contain explicitly classified local-only
    modules. Runtime verification never allows them, even as extra files.
    """
    result = set(FIXED_FILES)
    for folder in ("backend", "frontend"):
        base = root / folder
        if not base.is_dir() or base.is_symlink():
            raise ManifestError("PAYLOAD_DIR_UNAVAILABLE")
        for file in base.rglob("*"):
            if file.is_dir():
                if file.is_symlink():
                    raise ManifestError("SYMLINK_DIRECTORY_DENIED")
                continue
            if file.name.endswith(".pyc") or "__pycache__" in file.parts:
                continue
            if file.suffix not in ALLOWED_SUFFIXES or file.is_symlink():
                raise ManifestError("UNEXPECTED_OR_SYMLINK_FILE")
            rel = file.relative_to(root).as_posix()
            if rel in LOCAL_ONLY_SOURCE_FILES:
                if not allow_local_only_source:
                    raise ManifestError("OPERATOR_ONLY_PAYLOAD_FORBIDDEN")
                continue
            result.add(rel)
    if len(result) > MAX_FILES:
        raise ManifestError("FILE_COUNT_BOUND_EXCEEDED")
    return result


def file_hash(root: Path, rel: str) -> tuple[int, str]:
    path = PurePosixPath(rel)
    if (not rel or path.is_absolute() or ".." in path.parts
            or rel != path.as_posix()
            or not (rel in FIXED_FILES or (
                path.parts[0] in {"backend", "frontend"}
                and path.suffix in ALLOWED_SUFFIXES))):
        raise ManifestError("INVALID_SOURCE_PATH")
    target = root.joinpath(*path.parts)
    if target.is_symlink() or not target.is_file():
        raise ManifestError("SOURCE_MISSING_OR_SYMLINK")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ManifestError("SOURCE_FILE_TOO_LARGE")
    blob = target.read_bytes()
    return len(blob), hashlib.sha256(blob).hexdigest()


def _unique_pairs(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ManifestError("DUPLICATE_JSON_KEY")
        d[k] = v
    return d


def verify(root: Path) -> dict:
    """Return a bounded, secret-free state; do not expose entire file bytes."""
    root = Path(root)
    result = {
        "schema": RESULT_SCHEMA,
        "scope": "LOCAL_FILE_HASH_SELF_CHECK_ONLY",
        "status": "UNAVAILABLE",
        "source_revision": None,
        "manifest_sha256": None,
        "listed_files": 0,
        "matched_files": 0,
        "mismatch_count": None,
        "reason_code": "SOURCE_MANIFEST_UNAVAILABLE",
        "source_authority": "NOT_CRYPTOGRAPHICALLY_VERIFIED",
        "execution_authorized": False,
        "production_qualified": False,
    }
    try:
        manifest = root / "source_manifest.json"
        if manifest.is_symlink() or not manifest.is_file():
            raise ManifestError("SOURCE_MANIFEST_UNAVAILABLE")
        raw = manifest.read_bytes()
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ManifestError("MANIFEST_TOO_LARGE")
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
        if (type(doc) is not dict or doc.get("schema") != SCHEMA
                or doc.get("source_repository") != SOURCE_REPO
                or type(doc.get("source_revision")) is not str
                or not SHA40.fullmatch(doc["source_revision"])):
            raise ManifestError("INVALID_SOURCE_IDENTITY")
        rows = doc.get("files")
        if type(rows) is not list or len(rows) > MAX_FILES:
            raise ManifestError("INVALID_FILE_TABLE")
        table = {}
        for row in rows:
            if (type(row) is not dict or type(row.get("path")) is not str
                    or type(row.get("bytes")) is not int or row["bytes"] < 0
                    or type(row.get("sha256")) is not str
                    or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
                    or row["path"] in table):
                raise ManifestError("INVALID_FILE_ENTRY")
            table[row["path"]] = row
        actual = source_files(root)
        result["listed_files"] = len(table)
        result["source_revision"] = doc["source_revision"]
        result["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
        if set(table) != actual:
            raise ManifestError("FILE_SET_DRIFT")
        bad = 0
        for rel, entry in table.items():
            length, digest = file_hash(root, rel)
            if length != entry["bytes"] or digest != entry["sha256"]:
                bad += 1
        result["matched_files"] = len(table) - bad
        result["mismatch_count"] = bad
        if bad:
            raise ManifestError("FILE_BYTES_DRIFT")
        result["status"] = "SELF_CONSISTENT"
        result["reason_code"] = None
    except (ManifestError, OSError, UnicodeError, ValueError, TypeError) as exc:
        result["reason_code"] = (
            str(exc) if isinstance(exc, ManifestError) else type(exc).__name__
        )
    return result

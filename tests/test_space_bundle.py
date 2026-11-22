"""Offline contract checks for the derived, hash-bound command-center Space."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import main
from backend.source_manifest import (
    LOCAL_ONLY_SOURCE_FILES, ManifestError, source_files, verify,
)
from scripts.build_command_center_space import BundleError, build_bundle, git_admission

SHA = "a" * 40


def fixture(root: Path) -> None:
    (root / "backend").mkdir()
    (root / "frontend").mkdir()
    (root / "backend" / "__init__.py").write_text("# Package\n")
    (root / "backend" / "handler.py").write_text("VALUE = True\n")
    (root / "backend" / "lake_operator_bridge.py").write_text("LOCAL_ONLY = True\n")
    (root / "backend" / "unified_ops.py").write_text("LOCAL_ONLY = True\n")
    (root / "frontend" / "index.html").write_text("<h1>Observe</h1>\n")
    (root / "Dockerfile").write_text("FROM scratch\n")
    (root / "requirements-space.txt").write_text("fastapi==0.143.2\n")
    (root / "LICENSE").write_text("Example fixture only\n")


class SourceManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "src"
        self.root.mkdir()
        fixture(self.root)
        self.out = Path(self.temp.name) / "space"

    def build(self):
        return build_bundle(self.root, self.out, SHA)

    def test_bundle_self_consistent_and_no_execution_authority(self):
        result = self.build()
        self.assertEqual(result["status"], "SELF_CONSISTENT")
        self.assertEqual(result["source_revision"], SHA)
        self.assertEqual(result["listed_files"], 5)
        self.assertEqual(result["matched_files"], 5)
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["production_qualified"])
        self.assertEqual(result["source_authority"], "NOT_CRYPTOGRAPHICALLY_VERIFIED")
        self.assertIn("sdk: docker", (self.out / "README.md").read_text())
        self.assertIn(SHA, (self.out / "README.md").read_text())
        self.assertTrue((self.out / "LICENSE").exists())
        self.assertFalse((self.out / "backend" / "lake_operator_bridge.py").exists())
        self.assertFalse((self.out / "backend" / "unified_ops.py").exists())
        with self.assertRaisesRegex(ManifestError, "OPERATOR_ONLY_PAYLOAD_FORBIDDEN"):
            source_files(self.root)
        self.assertEqual(
            source_files(self.root, allow_local_only_source=True),
            {"Dockerfile", "requirements-space.txt",
             "backend/__init__.py", "backend/handler.py", "frontend/index.html"},
        )

    def test_modified_payload_fails_closed(self):
        self.build()
        (self.out / "backend" / "handler.py").write_text("VALUE = False\n")
        result = verify(self.out)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason_code"], "FILE_BYTES_DRIFT")
        self.assertEqual(result["mismatch_count"], 1)

    def test_missing_payload_fails_closed(self):
        self.build()
        (self.out / "frontend" / "index.html").unlink()
        self.assertEqual(verify(self.out)["reason_code"], "FILE_SET_DRIFT")

    def test_unlisted_extra_file_fails_closed(self):
        self.build()
        (self.out / "backend" / "evil.py").write_text("ACTION = True\n")
        self.assertEqual(verify(self.out)["reason_code"], "FILE_SET_DRIFT")

    def test_local_operator_bridge_in_deployed_bundle_is_explicitly_denied(self):
        self.build()
        forbidden = self.out / "backend" / "lake_operator_bridge.py"
        self.assertFalse(forbidden.exists())
        forbidden.write_text("LOCAL_ONLY = False\n")
        report = verify(self.out)
        self.assertEqual(report["status"], "UNAVAILABLE")
        self.assertEqual(report["reason_code"], "OPERATOR_ONLY_PAYLOAD_FORBIDDEN")
        self.assertFalse(report["execution_authorized"])

    def test_checkout_only_code_is_excluded_by_git_admission(self):
        tracked = (
            "Dockerfile", "requirements-space.txt",
            "backend/__init__.py", "backend/handler.py",
            "backend/lake_operator_bridge.py", "backend/unified_ops.py",
            "frontend/index.html",
        )
        def fake_git(root, *args):
            if args == ("status", "--porcelain"):
                return ""
            if args == ("branch", "--show-current"):
                return "main"
            if args == ("rev-parse", "HEAD"):
                return SHA
            if args == ("remote", "get-url", "origin"):
                return "https://github.com/szl-holdings/szl-command-center.git"
            if args == ("ls-remote", "origin", "refs/heads/main"):
                return SHA + " refs/heads/main"
            if args[0] == "ls-files":
                return "\n".join(tracked)
            raise AssertionError("unexpected git admission command")
        with patch("scripts.build_command_center_space._git", side_effect=fake_git):
            selected = git_admission(self.root, SHA)
        self.assertEqual(selected, set(tracked) - LOCAL_ONLY_SOURCE_FILES)
        self.assertNotIn("backend/lake_operator_bridge.py", selected)
        self.assertNotIn("backend/unified_ops.py", selected)
        report = build_bundle(self.root, self.out, SHA, selected=selected)
        self.assertEqual(report["status"], "SELF_CONSISTENT")

    def test_canonical_repository_operator_code_remains_local_only(self):
        root = Path(__file__).resolve().parents[1]
        path = root / "backend" / "lake_operator_bridge.py"
        self.assertTrue(path.is_file())
        expected = source_files(root, allow_local_only_source=True)
        self.assertNotIn("backend/lake_operator_bridge.py", expected)
        self.assertNotIn("backend/unified_ops.py", expected)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "space"
            report = build_bundle(root, out, SHA, selected=expected)
            self.assertEqual(report["status"], "SELF_CONSISTENT")
            self.assertFalse((out / "backend" / "lake_operator_bridge.py").exists())
            self.assertFalse((out / "backend" / "unified_ops.py").exists())
            manifest = json.loads((out / "source_manifest.json").read_text())
            self.assertFalse(any(
                row["path"] == "backend/lake_operator_bridge.py"
                for row in manifest["files"]
            ))


    def test_operator_console_in_public_bundle_is_explicitly_denied(self):
        self.build()
        module = self.out / "backend" / "unified_ops.py"
        self.assertFalse(module.exists())
        module.write_text("SHOULD_NEVER_SHIP = True\n")
        report = verify(self.out)
        self.assertEqual(report["status"], "UNAVAILABLE")
        self.assertEqual(report["reason_code"], "OPERATOR_ONLY_PAYLOAD_FORBIDDEN")

    def test_canonical_public_bundle_imports_without_operator_module(self):
        root = Path(__file__).resolve().parents[1]
        selected = source_files(root, allow_local_only_source=True)
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / "bundle"
            result = build_bundle(root, bundle, SHA, selected=selected)
            self.assertEqual(result["status"], "SELF_CONSISTENT")
            self.assertFalse((bundle / "backend" / "unified_ops.py").exists())
            statement = (
                "from backend import main; "
                "from backend import public_preview; "
                "assert public_preview.active(); "
                "assert main.unified_operator_router is None; "
                "assert not any(getattr(r, 'path', '').startswith('/ops/unified') "
                "or getattr(r, 'path', '').startswith('/api/ops/unified') "
                "for r in main.app.routes); "
                "print('PUBLIC_CONTAINER_OPERATOR_CODE_EXCLUDED')"
            )
            completed = subprocess.run(
                [sys.executable, "-B", "-c", statement],
                cwd=str(bundle), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=20,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("PUBLIC_CONTAINER_OPERATOR_CODE_EXCLUDED", completed.stdout)

    def test_invalid_manifest_duplicate_key_fails_closed(self):
        self.build()
        (self.out / "source_manifest.json").write_text('{"schema":"a","schema":"b"}')
        self.assertEqual(verify(self.out)["reason_code"], "DUPLICATE_JSON_KEY")

    def test_changed_source_manifest_identity_denied(self):
        self.build()
        f = self.out / "source_manifest.json"
        data = json.loads(f.read_text())
        data["source_revision"] = "BAD"
        f.write_text(json.dumps(data))
        self.assertEqual(verify(self.out)["reason_code"], "INVALID_SOURCE_IDENTITY")

    def test_missing_manifest_is_unavailable_not_green(self):
        self.assertEqual(verify(self.root)["status"], "UNAVAILABLE")

    def test_output_not_empty_denied(self):
        self.out.mkdir()
        (self.out / "existing").write_text("do not delete")
        with self.assertRaisesRegex(BundleError, "OUTPUT_NOT_EMPTY"):
            self.build()
        self.assertEqual((self.out / "existing").read_text(), "do not delete")

    def test_selected_source_drift_denied(self):
        with self.assertRaisesRegex(BundleError, "SOURCE_CLOSURE_DRIFT"):
            build_bundle(self.root, self.out, SHA, selected={"Dockerfile"})

    def test_bad_revision_denied_before_writing(self):
        with self.assertRaisesRegex(BundleError, "INVALID_SOURCE_REVISION"):
            build_bundle(self.root, self.out, "incomplete")
        self.assertFalse(self.out.exists())

    def test_http_route_never_reports_authority(self):
        report = self.build()
        with patch.object(main, "verify_source_manifest", return_value=report):
            response = main.api_source_manifest()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(json.loads(response.body)["execution_authorized"])
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_missing_runtime_manifest_returns_503(self):
        report = verify(self.root)
        with patch.object(main, "verify_source_manifest", return_value=report):
            response = main.api_source_manifest()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.body)["status"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()

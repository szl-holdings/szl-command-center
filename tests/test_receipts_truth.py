"""Receipt verifier output-contract regressions; subprocess calls are mocked."""
import subprocess
import unittest
from unittest.mock import patch

from backend.collectors import receipts
from backend.collectors.base import UNKNOWN, VERIFIED


class ReceiptVerifierTruthTests(unittest.TestCase):
    def run_verifier(self, stdout, returncode, stderr=""):
        completed = subprocess.CompletedProcess(
            ["python3", receipts.VERIFIER, receipts.BUNDLE],
            returncode,
            stdout=stdout,
            stderr=stderr,
        )
        with patch.object(receipts.os.path, "exists", return_value=True), patch.object(
            receipts.subprocess, "run", return_value=completed
        ) as run:
            result = receipts._run_verifier()
        run.assert_called_once_with(
            ["python3", receipts.VERIFIER, receipts.BUNDLE],
            capture_output=True,
            text=True,
            timeout=receipts.VERIFY_TIMEOUT,
        )
        return result

    def test_exact_exit_codes_verify_each_verdict(self):
        self.assertEqual(
            receipts.FINAL_EXIT_CODES,
            {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2},
        )
        for verdict, returncode in receipts.FINAL_EXIT_CODES.items():
            with self.subTest(verdict=verdict):
                result = self.run_verifier(
                    f"[{verdict}] fixture: checked\nFINAL: {verdict}\n",
                    returncode,
                )
                self.assertEqual(result["truth_state"], VERIFIED)
                self.assertEqual(result["value"]["verdict"], verdict)
                self.assertEqual(
                    result["value"]["checks"],
                    [{"state": verdict, "check": "fixture", "detail": "checked"}],
                )

    def test_exit_verdict_mismatch_is_unknown(self):
        for verdict, returncode in (
            ("PASS", 1),
            ("FAIL", 0),
            ("INCOMPLETE", 0),
        ):
            with self.subTest(verdict=verdict, returncode=returncode):
                result = self.run_verifier(f"FINAL: {verdict}\n", returncode)
                self.assertEqual(result["truth_state"], UNKNOWN)
                self.assertEqual(result["value"]["reported_verdict"], verdict)
                self.assertEqual(result["value"]["returncode"], returncode)
                self.assertEqual(
                    result["value"]["expected_returncode"],
                    receipts.FINAL_EXIT_CODES[verdict],
                )
                self.assertNotIn("verdict", result["value"])
                self.assertIn("disagrees with exit status", result["reason"])

    def test_multiple_or_conflicting_final_lines_are_unknown(self):
        cases = (
            ("FINAL: PASS\nFINAL: PASS\n", "", 0, ["PASS", "PASS"]),
            ("FINAL: FAIL\nFINAL: PASS\n", "", 0, ["FAIL", "PASS"]),
            ("FINAL: PASS\n", "FINAL: FAIL\n", 0, ["PASS", "FAIL"]),
        )
        for stdout, stderr, returncode, verdicts in cases:
            with self.subTest(stdout=stdout, stderr=stderr):
                result = self.run_verifier(stdout, returncode, stderr)
                self.assertEqual(result["truth_state"], UNKNOWN)
                self.assertEqual(result["value"]["reported_verdicts"], verdicts)
                self.assertEqual(result["value"]["returncode"], returncode)
                self.assertNotIn("verdict", result["value"])
                self.assertIn("multiple FINAL verdict lines", result["reason"])

    def test_missing_final_line_remains_unknown(self):
        result = self.run_verifier("[PASS] fixture: checked\n", 0)
        self.assertEqual(result["truth_state"], UNKNOWN)
        self.assertEqual(
            result["value"]["checks"],
            [{"state": "PASS", "check": "fixture", "detail": "checked"}],
        )
        self.assertIn("no FINAL verdict line", result["reason"])


if __name__ == "__main__":
    unittest.main()

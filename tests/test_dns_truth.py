"""Offline DNS observations must not masquerade as DNSSEC validation."""

import subprocess
import unittest
from unittest.mock import patch

from backend.collectors import dns


DS = "2371 13 2 " + "AB" * 32
NS = "ns1.example.net."


class DnsTruthTests(unittest.TestCase):
    def observe(self, ds=DS, ns=NS):
        def result(args, **kwargs):
            self.assertEqual(args[0:2], ["dig", "+short"])
            self.assertEqual(kwargs["timeout"], dns.DIG_TIMEOUT)
            return subprocess.CompletedProcess(args, 0, ds if args[2] == "DS" else ns, "")

        with patch.object(dns.shutil, "which", return_value="/usr/bin/dig"), patch.object(
            dns.subprocess, "run", side_effect=result
        ):
            return dns._domain("example.net")

    def test_diagnostic_stdout_cannot_be_verified(self):
        for stdout in (";; missing question section", ";; communications error", "connection timed out"):
            with self.subTest(stdout=stdout):
                result = self.observe(ds=stdout)
                self.assertEqual(result["truth_state"], "UNAVAILABLE")
                self.assertIsNone(result["value"])

    def test_mixed_record_and_diagnostic_rejects_whole_observation(self):
        self.assertEqual(self.observe(ds=DS + "\n;; missing question section")["truth_state"], "UNAVAILABLE")

    def test_invalid_ds_structure_is_unavailable(self):
        for stdout in ("1 13 2 GG", "1 13 2 ABC", "65536 13 2 AB", "-1 13 2 AB", "1 256 2 AB", "1 0 2 AB", "1 13 0 AB", "1 13 256 AB", "1 13 2 AB extra", "1 13 2"):
            with self.subTest(stdout=stdout):
                self.assertEqual(self.observe(ds=stdout)["truth_state"], "UNAVAILABLE")

    def test_invalid_nameserver_output_is_unavailable(self):
        for stdout in (";; missing question section", "ns1.example.net. comment", "-bad.example.net.", "bad-.example.net.", "bad..example.net.", "a" * 64 + ".example.net.", "not-a-fqdn", "."):
            with self.subTest(stdout=stdout):
                self.assertEqual(self.observe(ns=stdout)["truth_state"], "UNAVAILABLE")

    def test_valid_records_are_preserved_without_claiming_chain_validation(self):
        result = self.observe(ds=DS + "\n", ns="ns2.example.net.\n" + NS)
        self.assertEqual(result["value"]["ds_records"], [DS])
        self.assertEqual(result["value"]["ns_records"], [NS, "ns2.example.net."])
        self.assertEqual(result["truth_state"], "UNKNOWN")
        self.assertEqual(result["value"]["dnssec"], "UNKNOWN")
        self.assertIn("not validated", result["reason"])

    def test_supported_digest_lengths_preserve_records_without_validating_chain(self):
        for digest_type, octets in ((1, 20), (2, 32), (4, 48)):
            with self.subTest(digest_type=digest_type):
                record = f"2371 13 {digest_type} " + "Ab" * octets
                result = self.observe(ds=record)
                self.assertEqual(result["truth_state"], "UNKNOWN")
                self.assertEqual(result["value"]["ds_records"], [record])
                self.assertEqual(result["value"]["dnssec"], "UNKNOWN")

    def test_truncated_and_extended_supported_digests_are_unavailable(self):
        for digest_type, octets in ((1, 20), (2, 32), (4, 48)):
            for length in (1, octets - 1, octets + 1):
                with self.subTest(digest_type=digest_type, octets=length):
                    result = self.observe(ds=f"2371 13 {digest_type} " + "AB" * length)
                    self.assertEqual(result["truth_state"], "UNAVAILABLE")
                    self.assertIsNone(result["value"])

    def test_unsupported_digest_types_do_not_become_observations(self):
        for digest_type in (3, 5, 6, 7, 253, 254, 255):
            with self.subTest(digest_type=digest_type):
                result = self.observe(ds=f"2371 13 {digest_type} " + "AB" * 32)
                self.assertEqual(result["truth_state"], "UNAVAILABLE")
                self.assertIsNone(result["value"])

    def test_empty_ds_is_unknown_not_proof_of_unsigned_zone(self):
        result = self.observe(ds="")
        self.assertEqual(result["truth_state"], "UNKNOWN")
        self.assertEqual(result["value"]["dnssec"], "UNKNOWN")
        self.assertEqual(result["value"]["ds_records"], [])

    def test_empty_nameserver_answer_does_not_fabricate_records(self):
        result = self.observe(ns="")
        self.assertEqual(result["truth_state"], "UNKNOWN")
        self.assertEqual(result["value"]["ns_records"], [])

    def test_missing_dig_does_not_start_subprocess(self):
        with patch.object(dns.shutil, "which", return_value=None), patch.object(dns.subprocess, "run") as run:
            self.assertEqual(dns._domain("example.net")["truth_state"], "UNAVAILABLE")
            run.assert_not_called()

    def test_nonzero_exit_and_timeout_are_unavailable(self):
        with patch.object(dns.shutil, "which", return_value="/usr/bin/dig"):
            with patch.object(dns.subprocess, "run", return_value=subprocess.CompletedProcess([], 9, DS, "failure")):
                self.assertEqual(dns._domain("example.net")["truth_state"], "UNAVAILABLE")
            with patch.object(dns.subprocess, "run", side_effect=subprocess.TimeoutExpired("dig", 10)):
                self.assertEqual(dns._domain("example.net")["truth_state"], "UNAVAILABLE")

    def test_aggregate_never_upgrades_unvalidated_domains(self):
        with patch.object(dns.shutil, "which", return_value="/usr/bin/dig"), patch.object(
            dns.subprocess, "run", side_effect=lambda args, **kwargs: subprocess.CompletedProcess(args, 0, DS if args[2] == "DS" else NS, "")
        ):
            result = dns.collect()
        self.assertEqual(result["truth_state"], "UNKNOWN")
        self.assertTrue(all(x["value"]["dnssec"] == "UNKNOWN" for x in result["value"].values()))


if __name__ == "__main__":
    unittest.main()

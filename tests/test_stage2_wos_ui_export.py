"""Focused unit tests for UI export planning and validating WoS tagged files.

No internet access, browser login or licensed source data used.
"""
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "stage2" / "wos_ui_export.py"
spec = importlib.util.spec_from_file_location("wos_ui_export", MODULE_PATH)
wos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wos)

FIXTURE = (
    "FN Clarivate Analytics Web of Science\nVR 1.0\n"
    "PT J\nTI Test first\nCR A author, DOI 10.1234/first\n"
    "   B author, DOI 10.1234/second\nNR 2\n"
    "UT WOS:111\nER\n"
    "PT J\nTI Test second\nNR 0\nUT WOS:222\nER\nEF\n"
).encode("utf-8")


class BatchExportTests(unittest.TestCase):
    def test_expected_53_batches_for_exploratory_count(self):
        jobs = wos.ranges(26195)
        self.assertEqual(len(jobs), 53)
        self.assertEqual(jobs[0], (1, 500))
        self.assertEqual(jobs[-1], (26001, 26195))
        self.assertEqual(sum(b-a+1 for a,b in jobs), 26195)

    def test_boundary_limits(self):
        self.assertEqual(wos.ranges(500), [(1, 500)])
        self.assertEqual(wos.ranges(501), [(1, 500), (501, 501)])
        self.assertEqual(wos.ranges(26195, start_from=501)[0], (501,1000))
        for params in [(0,500,1), (1,501,1), (10,500,2)]:
            with self.assertRaises(ValueError):
                wos.ranges(*params)

    def test_tagged_export_audit_and_sha(self):
        import hashlib
        report = wos.audit_export(FIXTURE, 2)
        self.assertEqual(report["records"], 2)
        self.assertEqual(report["cited_references"], 2)
        self.assertEqual(report["sha256"], hashlib.sha256(FIXTURE).hexdigest())
        self.assertEqual(report["uids"], ["WOS:111", "WOS:222"])

    def test_fail_closed_truncation_and_duplicate(self):
        for data, count in [
            (FIXTURE, 3),
            (FIXTURE.replace(b"EF\n", b""), 2),
            (FIXTURE.replace(b"NR 2", b"NR 3"), 2),
            (FIXTURE.replace(b"WOS:222", b"WOS:111"), 2),
            (FIXTURE.replace(b"WOS:222", b"INVALID"), 2),
        ]:
            with self.subTest(data=data[-60:], count=count):
                with self.assertRaises(wos.ExportError):
                    wos.audit_export(data, count)


if __name__ == "__main__":
    unittest.main()

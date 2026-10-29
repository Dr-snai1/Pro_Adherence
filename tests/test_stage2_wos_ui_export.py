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



class _FakeInput:
    def __init__(self, is_radio=False):
        self.checked = False
        self.value = ""
        self.is_radio = is_radio

    def check(self):
        self.checked = True

    def is_checked(self):
        return self.checked

    def fill(self, value):
        self.value = value

    def input_value(self):
        return self.value

    def is_enabled(self):
        return not self.is_radio or self.checked

    def is_visible(self):
        return True


class _FakeLocator:
    def __init__(self, items):
        self.items = items

    def count(self):
        return len(self.items)

    @property
    def first(self):
        return self.items[0]

    def nth(self, n):
        return self.items[n]


class _FakeExportModal:
    def __init__(self, radio_count=2):
        self.radios = [_FakeInput(True) for _ in range(radio_count)]
        self.inputs = [_FakeInput(), _FakeInput()]

    def get_by_role(self, *args, **kwargs):
        return _FakeLocator([])

    def locator(self, selector):
        if "input[type=radio]" == selector:
            return _FakeLocator(self.radios)
        if "input[type=\"number\"]" in selector:
            return _FakeLocator(self.inputs)
        return _FakeLocator([])


class UiRangeCalibrationTests(unittest.TestCase):
    def test_records_from_radio_checked_before_export(self):
        modal = _FakeExportModal()
        wos.fill_range(modal, 501, 1000)
        self.assertTrue(modal.radios[1].checked)
        self.assertFalse(modal.radios[0].checked)
        self.assertEqual([n.value for n in modal.inputs], ["501", "1000"])

    def test_export_range_does_not_trust_one_radio(self):
        with self.assertRaisesRegex(wos.ExportError, "Records from"):
            wos.fill_range(_FakeExportModal(radio_count=1), 1, 500)

    def test_hard_limit_full_record_cited_references(self):
        with self.assertRaisesRegex(wos.ExportError, "500"):
            wos.fill_range(_FakeExportModal(), 1, 501)


if __name__ == "__main__":
    unittest.main()

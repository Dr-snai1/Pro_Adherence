"""Stage 2 offline checks for the *owner-approved* C: -> private Drive exporter.

Synthetic fixtures only. These tests do NOT claim live Google Drive or WoS UI
compatibility; the production script stops on unknown browser UI.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "stage2"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("wos_drive_session", SCRIPTS / "wos_drive_session.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class MockBody:
    def __init__(self, text):
        self.text = text

    def inner_text(self, **kwargs):
        return self.text


class MockPage:
    def __init__(self, url, text):
        self.url = url
        self.text = text

    def locator(self, path):
        assert path == "body"
        return MockBody(self.text)


class DriveArchivePlanTests(unittest.TestCase):
    def test_first_500_are_not_downloaded_twice(self):
        jobs = runner.ranges(runner.EXPECTED_TOTAL, start_from=501)
        self.assertEqual(jobs[0], (501, 1000))
        self.assertEqual(jobs[-1], (30501, 30635))
        self.assertEqual(len(jobs), 61)
        self.assertEqual(sum(end-start+1 for start, end in jobs), 30135)
        init = runner.manifest_default()
        self.assertEqual(init["first_batch_existing"]["drive_file_id"],
                         runner.FIRST_SOURCE_ID)
        self.assertEqual(init["first_batch_existing"]["sha256"],
                         runner.FIRST_SOURCE_SHA)
        self.assertFalse(init["cleanup_allowed"])
        self.assertEqual(init["new_batches"], [])

    def test_manifest_rejects_wrong_search_and_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.json"
            init = runner.manifest_default()
            runner.persist_state(path, init)
            self.assertEqual(runner.read_state(path), init)
            for mutation in [{"expected_results": 100},
                             {"folder_id": "wrong"},
                             {"schema": "changed"}]:
                changed = dict(init, **mutation)
                path.write_text(json.dumps(changed), encoding="utf8")
                with self.assertRaises(runner.ExportError):
                    runner.read_state(path)

    def test_source_search_preflight_requires_full_count_and_filters(self):
        text = ("30,635 results from Web of Science Core Collection\n"
                'TS=("medication adherence" OR "pharmionics")\n'
                "Document Types: Article\nLanguages: English\n")
        page = MockPage("https://www.webofscience.com/wos/woscc/summary/example", text)
        runner.preflight_wos(page)
        for bad in (text.replace("30,635", "26,195"),
                    text.replace("Document Types: Article", "Document Types: Review"),
                    text.replace("Languages: English", "Languages: French")):
            with self.subTest(bad=bad[-70:]):
                with self.assertRaises(runner.ExportError):
                    runner.preflight_wos(MockPage(page.url, bad))

    def test_single_zip_for_normal_chrome_contains_only_selected_files(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp) / "DELIVER_TO_PRIVATE_GOOGLE_DRIVE"
            d.mkdir()
            for name, data in (
                ("WOS_CORE_20261029_000501-001000.txt", b"source from WoS"),
                ("WOS_STAGE2_20261029_MANIFEST.json", b'{"status":"pending"}'),
                ("WOS_STAGE2_20261029_REPRO_SCRIPTS.zip", b"sample script bundle"),
            ):
                (d / name).write_bytes(data)
            archive = Path(temp) / "WOS_STAGE2_ALL_REMAINING_501-30635.zip"
            report = runner.build_full_archive(d, archive, expected_file_count=3)
            self.assertEqual(report["member_count"], 3)
            self.assertEqual(report["sha256"], runner.sha(archive))
            with ZipFile(archive) as zf:
                self.assertEqual(set(zf.namelist()), set(p.name for p in d.iterdir()))
                for p in d.iterdir():
                    self.assertEqual(zf.read(p.name), p.read_bytes())
            self.assertTrue(all(p.exists() for p in d.iterdir()))
            with self.assertRaisesRegex(runner.ExportError, "Expected 4"):
                runner.build_full_archive(d, archive, expected_file_count=4)

    def test_no_automated_google_sign_in_in_browser_runner(self):
        source = (SCRIPTS / "wos_drive_session.py").read_text(encoding="utf-8")
        self.assertNotIn('drive.goto(', source)
        self.assertNotIn('drive_upload(', source)
        self.assertIn('webbrowser.open(', source)
        self.assertIn('start_from=501', source)
        self.assertIn('https://libguides.brunel.ac.uk/az/databases?a=w', source)
        self.assertNotIn('wos.goto("https://www.webofscience.com/wos/woscc/basic-search"', source)

    def test_repro_scripts_are_archived_exactly(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = []
            for i in range(3):
                p = Path(temp) / f"script_{i}.py"
                p.write_bytes(f"example {i}\n".encode())
                paths.append(p)
            out = Path(temp) / "repro.zip"
            runner.make_repro_package(paths, out)
            with ZipFile(out) as zf:
                self.assertEqual(sorted(zf.namelist()), sorted(p.name for p in paths))
                for p in paths:
                    self.assertEqual(zf.read(p.name), p.read_bytes())
            self.assertEqual(runner.sha(out), __import__("hashlib").sha256(out.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()

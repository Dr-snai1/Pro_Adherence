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
                    text.replace("Languages: English", "Languages: French"),
                    text.replace("TS=(", "TI=(")):
            with self.subTest(bad=bad[-70:]):
                with self.assertRaises(runner.ExportError):
                    runner.preflight_wos(MockPage(page.url, bad))

    def test_drive_folder_accepts_google_account_routing_not_wrong_folder(self):
        body = "My Drive New"
        root = "https://drive.google.com/drive/folders/" + runner.DRIVE_FOLDER_ID
        with_account = ("https://drive.google.com/drive/u/0/folders/" + runner.DRIVE_FOLDER_ID)
        runner.verify_drive_folder(MockPage(root, body))
        runner.verify_drive_folder(MockPage(with_account, body))
        with self.assertRaises(runner.ExportError):
            runner.verify_drive_folder(MockPage(root.replace(runner.DRIVE_FOLDER_ID, "12345"), body))
        with self.assertRaises(runner.ExportError):
            runner.verify_drive_folder(MockPage(root, "Request access"))

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

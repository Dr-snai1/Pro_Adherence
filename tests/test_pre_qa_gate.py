import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

R = Path(__file__).resolve().parents[1]
S = importlib.util.spec_from_file_location('preqa', R / 'scripts/pre_qa_gate.py')
M = importlib.util.module_from_spec(S)
S.loader.exec_module(M)


class T(unittest.TestCase):
    def test_lock_exact(self):
        self.assertEqual(M.lock('attrs==25.4.0\n'), ({'attrs': '25.4.0'}, []))

    def test_lock_range_fails(self):
        self.assertTrue(M.lock('attrs>=25.4.0\n')[1])

    def test_history_marker(self):
        self.assertTrue(M.hist('> **SUPERSEDED**\n# x'))
        self.assertFalse(M.hist('# x\ncurrent'))

    def test_forbidden_paths(self):
        self.assertTrue(M.forbid('data/restricted/x', M.CF))
        self.assertTrue(M.forbid('.env.local', M.CF))
        self.assertFalse(M.forbid('docs/ENVIRONMENT.md', M.CF))

    def test_expected_parent_parameter_accepts_exact_relation(self):
        sha, parent = 'a' * 40, 'b' * 40
        def fake(*args):
            if args == ('git', 'rev-parse', 'HEAD'):
                return sha
            if args == ('git', 'rev-parse', 'HEAD^'):
                return parent
            raise AssertionError(args)
        with mock.patch.object(M, 'sh', side_effect=fake):
            self.assertEqual(M.git_identity_errors(sha, parent), [])

    def test_wrong_expected_parent_fails(self):
        sha, actual_parent, expected_parent = 'a' * 40, 'b' * 40, 'c' * 40
        def fake(*args):
            if args == ('git', 'rev-parse', 'HEAD'):
                return sha
            if args == ('git', 'rev-parse', 'HEAD^'):
                return actual_parent
            raise AssertionError(args)
        with mock.patch.object(M, 'sh', side_effect=fake):
            self.assertIn('HEAD^ != expected parent', M.git_identity_errors(sha, expected_parent))

    def test_wrong_expected_sha_fails(self):
        actual_sha, expected_sha, parent = 'a' * 40, 'b' * 40, 'c' * 40
        def fake(*args):
            if args == ('git', 'rev-parse', 'HEAD'):
                return actual_sha
            if args == ('git', 'rev-parse', 'HEAD^'):
                return parent
            raise AssertionError(args)
        with mock.patch.object(M, 'sh', side_effect=fake):
            self.assertIn('HEAD != expected SHA', M.git_identity_errors(expected_sha, parent))

    def test_wrong_runtime_fails(self):
        self.assertTrue(M.runtime_errors((3, 13, 5)))
        self.assertEqual(M.runtime_errors((3, 13, 16)), [])


class RuntimeRunnerTests(unittest.TestCase):
    def test_oci_reference_is_digest_pinned_linux_amd64_and_clears_pythonpath(self):
        text = (R / 'scripts/run_pre_qa_exact_runtime.sh').read_text()
        self.assertIn("IMAGE='python@sha256:8fb4cfa1a2616d7b8e0c2175cc6ad68f5729c34ea8488c0b360d2934b7be9024'", text)
        self.assertNotIn("IMAGE='python:3.13.16-slim'", text)
        self.assertIn("PLATFORM='linux/amd64'", text)
        self.assertIn('env -u PYTHONPATH', text)
        self.assertNotIn('--env PYTHONPATH=', text)

    def test_runtime_runner_propagates_engine_failure(self):
        runner = R / 'scripts/run_pre_qa_exact_runtime.sh'
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / 'fake-engine'
            fake.write_text("#!/usr/bin/env bash\ncase \"$1\" in pull) exit 0;; run) exit 23;; *) exit 24;; esac\n")
            fake.chmod(0o755)
            env = os.environ.copy()
            env['QA_CONTAINER_ENGINE'] = str(fake)
            p = subprocess.run(
                ['bash', str(runner), '--expected-sha', 'a' * 40,
                 '--expected-parent', 'b' * 40, '--architecture-revision', '22'],
                cwd=R, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual(p.returncode, 23, p.stderr.decode())

    def test_source_fallback_identity_is_exact(self):
        text = (R / 'scripts/run_pre_qa_source_fallback.sh').read_text()
        self.assertIn("SOURCE_URL='https://www.python.org/ftp/python/3.13.16/Python-3.13.16.tar.xz'", text)
        self.assertIn("SOURCE_SHA256='f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d'", text)
        self.assertLess(text.index('ACTUAL_SHA='), text.index('tar -xJf'))

    def test_previous_preqa_record_is_superseded(self):
        old = (R / 'docs/handoffs/PRE_QA_STAGE0_ENVIRONMENT_2026-10-08.md').read_text()
        self.assertTrue(M.hist(old))


if __name__ == '__main__':
    unittest.main()

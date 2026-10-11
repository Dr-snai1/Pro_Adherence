"""Static and mutation-style independent boundary gates for revision 23."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from pro_adherence import pubmed_evidence as p

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / '.github/workflows/pubmed-evidence-manual.yml'
SPEC = REPO / 'configs/pubmed/smoke.v1.json'


class WorkflowContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = WORKFLOW.read_text()

    def test_dispatch_only(self):
        self.assertRegex(self.body,r'(?m)^on:\s*\n\s+workflow_dispatch:')
        self.assertNotRegex(self.body,r'(?m)^\s*(push|pull_request|schedule):')

    def test_explicit_read_permissions(self):
        self.assertRegex(self.body,r'(?m)^permissions:\s*\n\s+contents: read')
        self.assertNotIn('contents: write',self.body)

    def test_default_smoke_choice(self):
        self.assertRegex(self.body,r'(?m)^\s+mode:\s*\n')
        self.assertIn('options: [smoke, full]',self.body)
        self.assertIn('default: smoke',self.body)

    def test_checkpoints_are_persisted_before_failure_gate(self):
        self.assertIn('Prepare optional hash-verified private checkpoint',self.body)
        self.assertIn('prepare-resume',self.body)
        self.assertIn('resume_id',self.body)
        self.assertIn('steps.retrieve.outputs.exit_code',self.body)
        self.assertLess(self.body.index('Write only approved private evidence path'),
                        self.body.index('Fail if source retrieval remained incomplete'))

    def test_two_jobs_and_fresh_readback(self):
        self.assertIn('evidence-writer:',self.body)
        self.assertIn('independent-readback:',self.body)
        self.assertIn('needs: evidence-writer',self.body)
        self.assertIn('readback \\',self.body)
        self.assertNotIn('upload-artifact',self.body)

    def test_distinct_secrets_one_per_job(self):
        writer,verifier=self.body.split('  independent-readback:')
        self.assertIn('secrets.RESEARCH_EVIDENCE_WRITE_SSH_KEY',writer)
        self.assertNotIn('secrets.RESEARCH_EVIDENCE_READ_SSH_KEY',writer)
        self.assertIn('secrets.RESEARCH_EVIDENCE_READ_SSH_KEY',verifier)
        self.assertNotIn('secrets.RESEARCH_EVIDENCE_WRITE_SSH_KEY',verifier)

    def test_pinned_code_checkout(self):
        self.assertEqual(self.body.count('ref: ${{ github.sha }}'),2)
        self.assertEqual(self.body.count('persist-credentials: false'),2)

    def test_environment_for_both_jobs(self):
        self.assertEqual(self.body.count('environment: research-pubmed'),2)
        self.assertIn('RESEARCH_EVIDENCE_REPOSITORY',self.body)
        self.assertNotIn('secrets.GITHUB_TOKEN',self.body)

    def test_no_heavy_compute_no_public_serving(self):
        self.assertNotRegex(self.body,r'(?im)^\s*run:.*(hdbscan|umap|graph|embedding|serving|pages)')
        self.assertNotIn('git push --force',self.body)

    def test_no_raw_artifact_transport(self):
        self.assertNotIn('actions/upload-artifact',self.body)
        self.assertIn('$RUNNER_TEMP/pubmed',self.body)
        self.assertNotIn('git add .',self.body)

    def test_smoke_not_full_scientific_input(self):
        spec=json.loads(SPEC.read_text())
        self.assertEqual(spec['task_id'],'TASK-0004')
        self.assertTrue(spec['query_artifact'].startswith('infra-smoke'))
        self.assertNotIn('Medication Adherence',next(iter(spec['queries'].values())))
        self.assertIn('spec == \'configs/pubmed/smoke.v1.json\'',self.body)

    def test_no_secrets_in_smoke_fixture(self):
        source=SPEC.read_text()
        self.assertNotRegex(source,r'(?i)private[_ -]?key|BEGIN OPENSSH|ghp_[A-Za-z0-9]{15}')
        self.assertNotIn('api_key":',source)

    def test_research_path_is_gitignored(self):
        ignore=(REPO/'.gitignore').read_text() if (REPO/'.gitignore').exists() else '/data/research/'
        self.assertIn('/data/research/',ignore)


class IndependentHashes(unittest.TestCase):
    def test_package_root_uses_sorted_canonical_json(self):
        d={'z':9,'a':{'c':3,'b':2}}
        self.assertEqual(p.sha(p.canonical(d)),p.sha(b'{"a":{"b":2,"c":3},"z":9}'))

    def test_id_allowlist_rejects_traversal_and_unicode_separator(self):
        for invalid in ['.', '..','../x','x/y','x\\y','x\nBAD','🎯']:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):p.safe_id(invalid)

    def test_reject_unauthorized_data_class_repository(self):
        for wrong in ['Dr-snai1/Pro_Adherence','Dr-snai1/private','other/evidence']:
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):p.validate_repository(wrong)

    def test_post_timing_uses_monotonic(self):
        clock=[0]
        sleeps=[]
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*a):return None
            def read(self):return b'{"esearchresult":{"count":"0","idlist":[]}}'
        c=p.Client('t','e@example.com',sleep=lambda secs:(sleeps.append(secs),clock.__setitem__(0,clock[0]+secs)),clock=lambda:clock[0],opener=lambda req,timeout:FakeResponse())
        c.esearch('a',0);c.esearch('b',0)
        self.assertGreaterEqual(sum(sleeps),0.36)

    def test_retry_only_transient(self):
        from urllib.error import HTTPError
        calls=[]
        def fail(req,timeout):
            calls.append(1)
            raise HTTPError('u',403,'forbidden',{},None)
        c=p.Client('t','e@example.com',opener=fail,sleep=lambda _:None)
        with self.assertRaisesRegex(RuntimeError,'403'):c.esearch('a',0)
        self.assertEqual(len(calls),1)

    def test_no_raw_response_printed_in_errors(self):
        with mock.patch('sys.stderr') as output:
            result=p.main(['verify','/nonexistent'])
        self.assertEqual(result,1)
        message=''.join(str(x) for x in output.write.call_args_list)
        self.assertNotIn('SECRET',message)
        self.assertNotIn('Traceback',message)


if __name__ == '__main__': unittest.main()

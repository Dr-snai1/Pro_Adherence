"""Negative/mutation controls for TASK-0004 candidate admission."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

R = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location("task0004_gate", R / "scripts/pre_qa_task0004.py")
g = importlib.util.module_from_spec(s)
s.loader.exec_module(g)
YAML = (R / ".github/workflows/pubmed-evidence-manual.yml").read_text()

class GateTests(unittest.TestCase):
    def test_exact_sha_parent_rev23_pass(self):
        sha = "a"*40
        self.assertEqual(g.identity_errors(sha, g.PARENT, git=lambda *a: sha if a[-1]=="HEAD" else g.PARENT), [])
        self.assertEqual(g.revision_errors("23"), [])

    def test_wrong_sha_rejected(self):
        self.assertIn("HEAD != exact SHA", g.identity_errors("a"*40, g.PARENT, git=lambda *a:"b"*40))

    def test_wrong_parent_rejected(self):
        self.assertTrue(g.identity_errors("a"*40, "b"*40, git=lambda *a:"a"*40))

    def test_non23_revisions_rejected(self):
        for rev in ("22", "24", "", "23.0"):
            self.assertTrue(g.revision_errors(rev))

    def test_dirty_tree_rejected(self):
        with mock.patch.object(g, "identity_errors", return_value=[]), \
             mock.patch.object(g, "file_errors", return_value=[]), \
             mock.patch.object(g, "sh", side_effect=lambda *args:" M docs/test.md" if args[1]=="status" else ""):
            issues = g.checks("a"*40, g.PARENT, "23")
        self.assertIn("dirty Git tree", issues)

    def test_missing_required_runner_workflow_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            errs = g.file_errors(Path(t))
        self.assertTrue(any("pubmed_evidence.py" in err for err in errs))
        self.assertTrue(any("pubmed-evidence-manual.yml" in err for err in errs))

    def test_forbidden_research_restricted_public_paths(self):
        for x in ("data/raw/a", "research/a", "data/restricted/a", "restricted/a",
                  "public/evidence/a", "serving/evidence/a", "docs/secrets.key", "../x"):
            with self.subTest(x=x):
                self.assertTrue(g.forbid(x))

    def test_stale_status_claim_detected(self):
        self.assertTrue(g.status_errors("docs/x.md", "Stage 1 — CLOSED"))
        self.assertTrue(g.status_errors("docs/x.md", "QA pending"))
        self.assertFalse(g.status_errors("docs/x.md", "See 07_STAGE_STATUS"))

    def test_historical_stage0_rev22_pin_preserved(self):
        t = (R / "scripts/pre_qa_gate.py").read_text()
        self.assertIn('HISTORICAL_STAGE0_PARENT = "6d81685431b11bbf8fa4d4410fa5945921c1b49a"', t)
        ci = (R / ".github/workflows/stage0-tests.yml").read_text()
        self.assertIn("--architecture-revision 22", ci)
        self.assertIn("--architecture-revision 23", ci)

class WorkflowMutationTests(unittest.TestCase):
    def test_original_valid(self):
        self.assertEqual(g.workflow_errors(YAML), [])

    def test_push_added_rejected(self):
        self.assertTrue(g.workflow_errors(YAML.replace("  workflow_dispatch:", "  push:\n  workflow_dispatch:", 1)))

    def test_pull_request_added_rejected(self):
        self.assertTrue(g.workflow_errors(YAML.replace("  workflow_dispatch:", "  pull_request:\n  workflow_dispatch:", 1)))

    def test_schedule_added_rejected(self):
        self.assertTrue(g.workflow_errors(YAML.replace("  workflow_dispatch:", "  schedule:\n  workflow_dispatch:", 1)))

    def test_inline_push_rejected(self):
        self.assertTrue(g.workflow_errors(YAML.replace("on:\n  workflow_dispatch:", "on: [workflow_dispatch, push]", 1)))

    def test_write_permission_rejected(self):
        self.assertTrue(g.workflow_errors(YAML.replace("  contents: read", "  contents: write", 1)))

    def test_extra_permission_rejected(self):
        self.assertTrue(g.workflow_errors(YAML.replace("  contents: read", "  contents: read\n  actions: write", 1)))

    def test_shared_deploy_key_slot_rejected(self):
        self.assertTrue(g.workflow_errors(YAML.replace("RESEARCH_EVIDENCE_READ_SSH_KEY", "RESEARCH_EVIDENCE_WRITE_SSH_KEY")))

    def test_missing_readback_commit_rejected(self):
        self.assertTrue(g.workflow_errors(YAML.replace("needs.evidence-writer.outputs.commit", "github.sha")))

    def test_unapproved_evidence_repo_rejected(self):
        self.assertTrue(g.workflow_errors(YAML.replace(g.REPO, "attacker/evidence")))

    def test_public_artifact_rejected(self):
        self.assertTrue(g.workflow_errors(YAML+"\nactions/upload-artifact"))

    def test_secret_source_and_approved_workflow_boundary(self):
        slot = "NCBI_EMAIL: $" + "{{ secrets.NCBI_EMAIL }}"
        self.assertIn(slot, YAML)
        self.assertNotIn("vars.NCBI_EMAIL", YAML)
        self.assertEqual(g.workflow_errors(YAML), [])

    def test_missing_secret_slot_rejected_for_correct_reason(self):
        slot = "NCBI_EMAIL: $" + "{{ secrets.NCBI_EMAIL }}"
        changed = YAML.replace(slot, "", 1)
        self.assertIn("retrieval NCBI_EMAIL must use Environment secret", g.workflow_errors(changed))

    def test_variable_email_source_rejected_for_correct_reason(self):
        slot = "NCBI_EMAIL: $" + "{{ secrets.NCBI_EMAIL }}"
        changed = YAML.replace(slot, "NCBI_EMAIL: $" + "{{ vars.NCBI_EMAIL }}", 1)
        self.assertIn("NCBI_EMAIL variable source forbidden", g.workflow_errors(changed))

    def test_direct_echo_or_printf_email_rejected_for_correct_reason(self):
        for command in ('echo "$NCBI_EMAIL"', 'printf "%s\\n" "$NCBI_EMAIL"'):
            with self.subTest(command=command):
                changed = YAML.replace("          result=$?",
                                       "          " + command + "\n          result=$?", 1)
                self.assertIn("explicit NCBI_EMAIL output/export forbidden",
                              g.workflow_errors(changed))

    def test_github_output_email_rejected_for_correct_reason(self):
        changed = YAML.replace('          result=$?',
                               '          echo "contact=$NCBI_EMAIL" >> "$GITHUB_OUTPUT"\n          result=$?', 1)
        self.assertIn("explicit NCBI_EMAIL output/export forbidden", g.workflow_errors(changed))

    def test_key_separation_rejected_for_correct_reason(self):
        writer = YAML.replace("RESEARCH_EVIDENCE_WRITE_SSH_KEY",
                              "RESEARCH_EVIDENCE_READ_SSH_KEY")
        self.assertIn("writer SSH slot wrong", g.workflow_errors(writer))
        verifier = YAML.replace("RESEARCH_EVIDENCE_READ_SSH_KEY",
                                "RESEARCH_EVIDENCE_WRITE_SSH_KEY")
        self.assertIn("read-only SSH slot wrong", g.workflow_errors(verifier))

    def test_read_probe_present_before_readback(self):
        self.assertEqual(g.workflow_errors(YAML), [])
        v = YAML.split("  independent-readback:", 1)[1]
        self.assertLess(v.index("git clone --quiet --no-checkout"),
                        v.index("push --dry-run origin"))
        self.assertLess(v.index("push --dry-run origin"),
                        v.index("pubmed_evidence readback"))

    def test_missing_or_real_push_rejected_for_correct_reason(self):
        for changed in (
            YAML.replace("push --dry-run origin", "push origin", 1),
            YAML.replace("push --dry-run origin", "push --force origin", 1),
            YAML.replace("push --dry-run origin",
                         "push --dry-run origin HEAD:refs/heads/other\n"
                         "          git push origin", 1),
        ):
            self.assertIn("read-only permission probe missing or unsafe Git push",
                          g.workflow_errors(changed))

    def test_probe_ref_mutation_rejected_for_correct_reason(self):
        changed = YAML.replace("refs/heads/__readback_permission_probe__",
                               "refs/heads/main", 1)
        self.assertIn("read-only permission probe missing or unsafe Git push",
                      g.workflow_errors(changed))

    def test_probe_order_rejected_for_correct_reason(self):
        marker = '          readback_flag=()'
        probe_start = '          # Independent negative-capability check; never update a private ref.\n'
        start = YAML.index(probe_start)
        stop = YAML.index(marker, start)
        changed = YAML[:start] + YAML[stop:].replace(
            '          rm -f "$key"',
            YAML[start:stop] + '          rm -f "$key"', 1)
        self.assertIn("read-only permission probe must precede exact readback after clone",
                      g.workflow_errors(changed))

    def test_probe_success_must_fail_closed(self):
        changed = YAML.replace("            exit 1\n          fi\n          readback_flag=()",
                               "            :\n          fi\n          readback_flag=()", 1)
        self.assertIn("read-only permission probe must fail closed",
                      g.workflow_errors(changed))

    def test_only_scoped_diff_paths_admitted(self):
        self.assertEqual(g.diff_errors(list(g.ALLOWED_CHANGED)), [])
        self.assertIn("forbidden candidate path: src/pro_adherence/pubmed_evidence.py",
                      g.diff_errors(["src/pro_adherence/pubmed_evidence.py"]))

if __name__ == "__main__":
    unittest.main()

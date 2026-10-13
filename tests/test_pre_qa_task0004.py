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


    def test_ncbi_email_variable_regression(self):
        self.assertTrue(g.workflow_errors(YAML.replace("secrets.NCBI_EMAIL", "vars.NCBI_EMAIL", 1)))

    def test_missing_email_secret_regression(self):
        self.assertTrue(g.workflow_errors(YAML.replace("secrets.NCBI_EMAIL", "vars.BAD_SLOT", 1)))

    def test_email_shell_echo_regression(self):
        self.assertTrue(g.workflow_errors(YAML.replace("          resume_flag=()", '          echo "$NCBI_EMAIL"\n          resume_flag=()', 1)))

    def test_email_python_print_regression(self):
        mutation = "          python -c 'import os; print(os.environ)'\\n          resume_flag=()"
        self.assertTrue(g.workflow_errors(YAML.replace("          resume_flag=()", mutation, 1)))

    def test_email_github_output_regression(self):
        self.assertTrue(g.workflow_errors(YAML.replace("          resume_flag=()", '          echo "NCBI_EMAIL=$NCBI_EMAIL" >> "$GITHUB_OUTPUT"\n          resume_flag=()', 1)))

    def test_read_probe_absent_regression(self):
        start = YAML.index('          git clone --quiet "git@github.com:$REPOSITORY.git" "$RUNNER_TEMP/pubmed-permission-probe"')
        end = YAML.index("          readback_flag=()", start)
        self.assertTrue(g.workflow_errors(YAML[:start] + YAML[end:]))

    def test_read_probe_inverted_regression(self):
        self.assertTrue(g.workflow_errors(YAML.replace(
            'if git -C "$RUNNER_TEMP/pubmed-permission-probe" push --dry-run',
            'if ! git -C "$RUNNER_TEMP/pubmed-permission-probe" push --dry-run', 1)))

    def test_read_probe_success_allowed_regression(self):
        self.assertTrue(g.workflow_errors(YAML.replace(
            "            exit 1\n          fi\n          readback_flag=()",
            "            exit 0\n          fi\n          readback_flag=()", 1)))

    def test_read_probe_real_push_regression(self):
        self.assertTrue(g.workflow_errors(YAML.replace(
            'push --dry-run "git@github.com:$REPOSITORY.git"',
            'push "git@github.com:$REPOSITORY.git"', 1)))

    def test_verifier_write_key_regression(self):
        self.assertTrue(g.workflow_errors(YAML.replace(
            "secrets.RESEARCH_EVIDENCE_READ_SSH_KEY",
            "secrets.RESEARCH_EVIDENCE_WRITE_SSH_KEY", 1)))


class SecuritySec001RealValidatorTests(unittest.TestCase):
    """All mutations run through the real production workflow_errors entrypoint."""

    @staticmethod
    def injected(script, step="          resume_flag=()"):
        assert step in YAML, "test must mutate a real executable run block"
        return YAML.replace(step, script + "\n" + step, 1)

    def rejected(self, script, reason, step="          resume_flag=()"):
        failures = g.workflow_errors(self.injected(script, step))
        self.assertTrue(any(reason in x for x in failures), failures)

    def test_sec001_baseline_exact_secure_workflow(self):
        self.assertEqual(g.workflow_errors(YAML), [])

    def test_sec001_one_line_control(self):
        self.rejected("          python -c 'import os; print(os.environ)'",
                      "whole-environment")

    def test_sec001_multiline_heredoc(self):
        self.rejected("          python - <<'PY'\n"
                      "          import os\n"
                      "          print(os.environ)\n"
                      "          PY", "whole-environment")

    def test_sec001_multiline_python_c(self):
        self.rejected("          python -c 'import os\n"
                      "          print(os.environ)'", "whole-environment")
        self.rejected("          python3 -c 'import os as o\n"
                      "          print(o.environ)'", "whole-environment")

    def test_sec001_alternate_step_run(self):
        # GitHub Actions accepts a direct - run: | list item with no step name.
        anchor = "      - name: Retrieve to isolated runner temporary storage"
        self.assertIn(anchor, YAML)
        dangerous = ("      - run: |\n"
                     "          python - <<'PY'\n"
                     "          import os\n"
                     "          print(dict(os.environ))\n"
                     "          PY\n")
        mutated = YAML.replace(anchor, dangerous + anchor, 1)
        self.assertTrue(any("whole-environment" in e
                            for e in g.workflow_errors(mutated)))
        harmless = YAML.replace(
            anchor, "      - run: |\n          echo 'env is ordinary text'\n" + anchor, 1)
        self.assertEqual(g.workflow_errors(harmless), [])

    def test_sec001_nested_shell(self):
        for cmd in ("bash -c 'env'", "sh -c 'printenv'",
                    "bash -c 'set -x'", "set", "export -p"):
            with self.subTest(cmd=cmd):
                wanted = ("shell tracing" if "set -x" in cmd
                          else "whole-environment")
                self.rejected("          " + cmd, wanted)

    def test_sec001_import_alias(self):
        self.rejected("          python3 - <<'PY'\n"
                      "          import os as o\n"
                      "          print(o.environ)\n"
                      "          PY", "whole-environment")

    def test_sec001_from_import_alias(self):
        self.rejected("          python - <<'PY'\n"
                      "          from os import environ as e\n"
                      "          print(e)\n"
                      "          PY", "whole-environment")

    def test_sec001_environment_forms(self):
        forms = (
            "import os\nprint(dict(os.environ))",
            "import os,json\nprint(json.dumps(dict(os.environ)))",
            "import os\nos.environ.copy()",
            "import os\nfor key in os.environ.items():\n    print(key)",
            "import os\npprint = print\npprint(os.environ)",
            "import os\nlist(os.environ)",
            "import os\nprint(getattr(os, 'environ'))",
        )
        for src in forms:
            with self.subTest(src=src):
                command = ("          python - <<'PY'\n" +
                           "\n".join("          " + x for x in src.splitlines()) +
                           "\n          PY")
                self.rejected(command, "whole-environment")

    def test_sec001_safe_specific_key(self):
        for src in ("import os\nprint(os.environ['RESULT_JSON'])",
                    "import os\nprint(os.environ.get('EXPECTED_ROOT'))",
                    "from os import environ as e\nprint(e.get('RESULT_JSON'))"):
            with self.subTest(src=src):
                command = ("          python - <<'PY'\n" +
                           "\n".join("          " + x for x in src.splitlines()) +
                           "\n          PY")
                self.assertEqual(g.workflow_errors(self.injected(command)), [])

    def test_sec001_shell_env_and_printenv(self):
        for cmd in ("env", "printenv", "env | sort", "printenv > dump.txt",
                    "X=safe env", "if env; then"):
            with self.subTest(cmd=cmd):
                self.rejected("          " + cmd, "whole-environment")

    def test_sec001_shell_trace(self):
        for cmd in ("set -x", "set -o xtrace", "bash -x test.sh", "sh -x test.sh"):
            with self.subTest(cmd=cmd):
                self.rejected("          " + cmd, "shell tracing")

    def test_sec001_explicit_ncbi_email_shell(self):
        for cmd in ('echo "$NCBI_EMAIL"', 'printf "%s" "$NCBI_EMAIL"',
                    'echo "NCBI_EMAIL=$NCBI_EMAIL" >> "$GITHUB_OUTPUT"'):
            with self.subTest(cmd=cmd):
                self.rejected("          " + cmd, "NCBI_EMAIL")

    def test_sec001_ncbi_email_github_output(self):
        self.rejected('          printf "NCBI_EMAIL=%s\\n" "$NCBI_EMAIL" >> "$GITHUB_OUTPUT"',
                      "NCBI_EMAIL")

    def test_sec001_public_variable(self):
        self.assertIn("Environment secret", " ".join(g.workflow_errors(
            YAML.replace("secrets.NCBI_EMAIL", "vars.NCBI_EMAIL", 1))))

    def test_sec001_read_probe_mandatory(self):
        self.assertEqual(g.workflow_errors(YAML), [])
        self.assertTrue(g.workflow_errors(YAML.replace("push --dry-run", "push", 1)))

    def test_sec001_all_secret_bearing_steps(self):
        # The same predicate must protect each actual secret-bearing step.
        blocks = (
            "          resume_flag=()",  # NCBI_EMAIL / NCBI_API_KEY
            "          test -n \"$SSH_KEY\"",  # writer SSH in resume step
            "          package=\"$(find",  # writer SSH in persist step
            "          readback_flag=()",  # read verifier SSH
        )
        for step in blocks:
            with self.subTest(step=step):
                self.rejected("          python - <<'PY'\n"
                              "          import os\n"
                              "          print(dict(os.environ))\n"
                              "          PY", "whole-environment", step=step)

    def test_sec001_shell_data_not_command(self):
        for cmd in ("echo 'env is a noun'", "MESSAGE=environment",
                    "printf '%s\\n' 'printenv is text'"):
            with self.subTest(cmd=cmd):
                self.assertEqual(g.workflow_errors(self.injected("          " + cmd)), [])

    def test_sec001_unparseable_security_python_fails_closed(self):
        self.rejected("          python3 - <<'PY'\n"
                      "          import os\n"
                      "          print(os.environ\n"
                      "          PY", "unparseable Python environment")


if __name__ == "__main__":
    unittest.main()

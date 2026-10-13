"""Regression: collector failures must reach the durable checkpoint writer.

This test exercises the exact GitHub Actions run script under bash -e, the
same shell option GitHub applies to a default Linux run step.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/pubmed-evidence-manual.yml"


def retrieval_shell_script():
    text = WORKFLOW.read_text(encoding="utf-8")
    start = "      - name: Retrieve to isolated runner temporary storage\n"
    finish = "      - name: Write only approved private evidence path\n"
    step = text.split(start, 1)[1].split(finish, 1)[0]
    body = step.split("        run: |\n", 1)[1]
    return "\n".join(line[10:] if line.startswith("          ") else line
                     for line in body.splitlines()) + "\n"


class TestCollectorExitCapture(unittest.TestCase):
    def test_failing_collector_does_not_skip_checkpoint_stage(self):
        self._assert_collector_status_is_recorded(17)

    def test_successful_collector_exit_is_also_recorded(self):
        self._assert_collector_status_is_recorded(0)

    def _assert_collector_status_is_recorded(self, code):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bindir = root / "bin"
            bindir.mkdir()
            mocked_python = bindir / "python"
            mocked_python.write_text(f"#!/bin/sh\nexit {code}\n", encoding="utf-8")
            mocked_python.chmod(0o755)
            output = root / "github_output"
            output.touch()
            env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}",
                   "INPUT_SPEC": "configs/pubmed/smoke.v1.json",
                   "INPUT_MODE": "full", "RESUME_ID": "",
                   "RUNNER_TEMP": str(root),
                   "GITHUB_SHA": "a" * 40,
                   "GITHUB_OUTPUT": str(output)}
            proc = subprocess.run(["bash", "-e", "-c", retrieval_shell_script()],
                                  env=env, capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(f"exit_code={code}\n", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

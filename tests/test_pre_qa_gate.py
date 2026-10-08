import importlib.util, unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]; S=importlib.util.spec_from_file_location('preqa',R/'scripts/pre_qa_gate.py'); M=importlib.util.module_from_spec(S); S.loader.exec_module(M)
class T(unittest.TestCase):
 def test_lock_exact(self): self.assertEqual(M.lock('attrs==25.4.0\n'),({'attrs':'25.4.0'},[]))
 def test_lock_range_fails(self): self.assertTrue(M.lock('attrs>=25.4.0\n')[1])
 def test_history_marker(self): self.assertTrue(M.hist('> **SUPERSEDED**\n# x')); self.assertFalse(M.hist('# x\ncurrent'))
 def test_forbidden_paths(self): self.assertTrue(M.forbid('data/restricted/x',M.CF)); self.assertTrue(M.forbid('.env.local',M.CF)); self.assertFalse(M.forbid('docs/ENVIRONMENT.md',M.CF))
if __name__=='__main__': unittest.main()

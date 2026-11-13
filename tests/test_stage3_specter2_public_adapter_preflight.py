"""Synthetic-only SPECTER2 public adapter source-contract tests."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SOURCE=Path(__file__).with_name('stage3_specter2_public_adapter_preflight.py')
spec=importlib.util.spec_from_file_location('specter2_probe',SOURCE)
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class AdapterPublicPreflightTests(unittest.TestCase):
    def fixture(self,p):
        o={'config':dict(probe.SEMANTICS),'hidden_size':768,
           'model_class':'BertAdapterModel','model_type':'bert',
           'name':'[PRX]','version':'3.1.0',
           'model_name':'allenai/specter_plus_plus'}
        p.write_text(json.dumps(o),encoding='utf-8')
        return o

    def test_config_only_stays_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'cfg.json';self.fixture(p)
            r=probe.audit(p)
            self.assertEqual(r['model']['adapter_revision'],probe.ADAPTER_REV)
            self.assertEqual(r['status'],'CONFIG_ONLY_RUNTIME_BLOCKED')
            self.assertFalse(any(r['gates'].values()))
            for key,value in [('reduction_factor',8),('output_adapter',False),('mh_adapter',True),('non_linearity','gelu')]:
                obj=self.fixture(p);obj['config'][key]=value
                p.write_text(json.dumps(obj),encoding='utf-8')
                with self.subTest(key=key),self.assertRaisesRegex(probe.Rejected,'semantics'):
                    probe.check_config(p)

    def test_wrong_adapter_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'cfg.json';obj=self.fixture(p);obj['name']='[CLS]'
            p.write_text(json.dumps(obj),encoding='utf-8')
            with self.assertRaisesRegex(probe.Rejected,'identity'):probe.check_config(p)

    def test_wellformed_unverified_weights_rejected_before_unpickle(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'model.bin'
            with zipfile.ZipFile(p,'w') as z:z.writestr('archive/data.pkl',b'example')
            with self.assertRaisesRegex(probe.Rejected,'SHA256 mismatch'):
                probe.check_weights(p)
            self.assertNotIn('torch.load',SOURCE.read_text())
            self.assertNotIn('pickle.load',SOURCE.read_text())

if __name__=='__main__':unittest.main()

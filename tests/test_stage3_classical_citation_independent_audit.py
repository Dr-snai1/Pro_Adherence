"""Source-free synthetic regression tests for the independent citation pair auditor."""
from __future__ import annotations
from contextlib import contextmanager
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"scripts"/"stage3_classical_citation_independent_audit.py"
spec=importlib.util.spec_from_file_location("independent_citations",SOURCE)
assert spec and spec.loader
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def networks():
    out=[set() for _ in range(6)]
    inc=[set() for _ in range(6)]
    for a,b in [(0,1),(0,2),(3,1),(3,2),(3,4),(5,2)]:
        out[a].add(b);inc[b].add(a)
    return out,inc


class IndependentCitationTests(unittest.TestCase):
    def test_expected_support_orientation(self):
        out,inc=networks()
        self.assertEqual(m.expected_support("co_citation",1,2,out,inc),2)
        self.assertEqual(m.expected_support("co_citation",1,4,out,inc),1)
        self.assertEqual(m.expected_support("bibliographic_coupling",0,3,out,inc),2)
        self.assertEqual(m.expected_support("bibliographic_coupling",0,5,out,inc),1)
        with self.assertRaises(ValueError):
            m.expected_support("unknown",0,3,out,inc)

    @contextmanager
    def toy_expected(self,model_name,rows,incidences,max_weight):
        original=m.EXPECTED[model_name]
        m.EXPECTED[model_name]={"rows":rows,"sum":incidences,
                                "max":max_weight,
                                "hist":{"1":rows-1,"2":1}}
        try:
            yield
        finally:
            m.EXPECTED[model_name]=original

    def emit(self, path, pairs):
        with gzip.GzipFile(filename="",fileobj=path.open("wb"),mtime=0,mode="wb") as f:
            for a,b,weight in pairs:
                f.write((json.dumps([a*m.N+b,weight])+"\n").encode("ascii"))

    def test_independent_co_citation_toy(self):
        out,inc=networks()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"pairs.gz"
            self.emit(path,[(1,2,2),(1,4,1),(2,4,1)])
            with self.toy_expected("co_citation",3,4,2):
                report=m.stream_verify(path,"co_citation",out,inc)
            self.assertEqual(report["rows"],3)
            self.assertEqual(report["sampled_exact_source_checks"],3)

    def test_independent_bibliographic_coupling_toy(self):
        out,inc=networks()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"pairs.gz"
            self.emit(path,[(0,3,2),(0,5,1),(3,5,1)])
            with self.toy_expected("bibliographic_coupling",3,4,2):
                report=m.stream_verify(path,"bibliographic_coupling",out,inc)
            self.assertEqual(report["rows"],3)

    def test_duplicate_pair_key_rejected(self):
        out,inc=networks()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"pairs.gz"
            self.emit(path,[(1,2,2),(1,2,2),(2,4,1)])
            with self.toy_expected("co_citation",3,5,2):
                with self.assertRaisesRegex(ValueError,"Out-of-order"):
                    m.stream_verify(path,"co_citation",out,inc)

    def test_independent_wrong_support_rejected(self):
        out,inc=networks()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"pairs.gz"
            self.emit(path,[(1,2,1),(1,4,1),(2,4,2)])
            with self.toy_expected("co_citation",3,4,2):
                with self.assertRaisesRegex(ValueError,"Independent source-vs-pair"):
                    m.stream_verify(path,"co_citation",out,inc)

    def test_gzip_crc_corruption_rejected(self):
        out,inc=networks()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"pairs.gz"
            self.emit(path,[(1,2,2),(1,4,1),(2,4,1)])
            payload=bytearray(path.read_bytes())
            payload[-5]^=0xA6
            path.write_bytes(payload)
            with self.toy_expected("co_citation",3,4,2):
                with self.assertRaises((OSError,EOFError,gzip.BadGzipFile)):
                    m.stream_verify(path,"co_citation",out,inc)


if __name__=="__main__":
    unittest.main()

"""Offline, network-independent validation of scoped NCBI evidence contract."""
import datetime as dt
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from pro_adherence import pubmed_evidence as p


QUERY = '("Medication Adherence"[mh] OR (drugs[tiab] AND taking[tiab]))'
SPEC = {"schema":"pubmed-run-spec/v1", "task_id":"TASK-0004", "query_artifact":"infra-smoke-v1",
        "queries":{"Q0":QUERY}, "operation":"esearch-pmids", "partition_policy":p.PARTITION_POLICY,
        "date_start":"1900-01-01", "date_end":"2099-12-31",
        "ncbi_config_refs":["NCBI_TOOL","NCBI_EMAIL","NCBI_API_KEY(optional)"]}


def response(count, ids=None, warning=None):
    return json.dumps({"esearchresult":{"count":str(count), "idlist":ids or [],
                       "querytranslation":"FAKE TRANSLATION", "warninglist":warning or {}}}).encode()


class FakeClient:
    def __init__(self, results):
        self.results = iter(results)
        self.sent = []

    def esearch(self, term, retmax):
        self.sent.append((term, retmax))
        return next(self.results), {"endpoint":p.ENDPOINT,"method":"POST", "utc":"2026-10-11T10:00:00Z", "retmax":retmax}


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.path = Path(self.t.name)
        self.env = mock.patch.dict(os.environ, {"PUBMED_CODE_COMMIT":"a"*40,
                                     "PUBMED_RUNTIME":"python-3.13.16", "NCBI_TOOL":"fixture-tool",
                                     "NCBI_EMAIL":"fixture@example.org"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def build(self, ids=("9","2","12"), *, warning=None):
        client = FakeClient([response(len(ids), warning=warning),response(len(ids),list(ids),warning)])
        destination = self.path / "package"
        result = p.collect(SPEC,"r-"+"1"*32,destination,client,timestamp="2026-10-11T10:00:00Z")
        return destination, result, client

    def test_exact_query_preserved_and_raw_bytes(self):
        root, _, client = self.build(warning={"quotedphrasesnotfound":["made-up"]})
        self.assertEqual((root/"queries/Q0.txt").read_bytes(), QUERY.encode())
        self.assertEqual(client.sent[0][0], QUERY)
        self.assertEqual((root/"raw/Q0/esearch/00001-count.json").read_bytes(),response(3,warning={"quotedphrasesnotfound":["made-up"]}))
        manifest = json.loads((root/"manifest.json").read_bytes())
        self.assertEqual(manifest["reconciliation"]["Q0"]["warninglist"], {"quotedphrasesnotfound":["made-up"]})
        self.assertEqual(manifest["reconciliation"]["Q0"]["querytranslation"], "FAKE TRANSLATION")

    def test_numeric_sorted_unique(self):
        self.assertEqual(p.numeric_pmids(["12","2","2","9"]),["2","9","12"])
        for bad in ["", "-3", "0", "01", "abc", "1.0"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                p.numeric_pmids([bad])
        root, _, _ = self.build()
        self.assertEqual((root/"pmids/Q0/union.txt").read_text(),"2\n9\n12\n")

    def test_deterministic_identity_and_spec_validation(self):
        spec = self.path/"spec.json"; spec.write_text(json.dumps(SPEC))
        self.assertEqual(p.read_spec(spec,mode="smoke",code_commit="a"*40,runtime="python-3.13.16"),
                         p.read_spec(spec,mode="smoke",code_commit="a"*40,runtime="python-3.13.16"))
        _, rid = p.read_spec(spec,mode="smoke",code_commit="a"*40,runtime="python-3.13.16")
        self.assertNotEqual(rid,p.read_spec(spec,mode="smoke",code_commit="b"*40,runtime="python-3.13.16")[1])
        bad=dict(SPEC, queries={"../bad":"x"})
        spec.write_text(json.dumps(bad))
        with self.assertRaises(ValueError): p.read_spec(spec,mode="smoke",code_commit="a"*40,runtime="x")

    def test_manifest_and_root_stable(self):
        a, info, _ = self.build()
        m=json.loads((a/"manifest.json").read_bytes()); root=m.pop("package_root_sha256")
        self.assertEqual(root,p.sha(p.canonical(m)))
        self.assertEqual(info["root_hash"],root)
        (self.path/"package").rename(self.path/"saved")
        b, again, _ = self.build()
        self.assertEqual((self.path/"saved/manifest.json").read_bytes(),(b/"manifest.json").read_bytes())
        self.assertEqual(info["root_hash"],again["root_hash"])

    def test_tamper_extra_and_count_invariants(self):
        root, _, _ = self.build()
        (root/"pmids/Q0/union.txt").write_text("3\n9\n12\n")
        with self.assertRaisesRegex(ValueError,"hash"):p.verify(root)
        (root/"pmids/Q0/union.txt").write_text("2\n9\n12\n")
        (root/"forbidden-extra").write_text("hello")
        with self.assertRaisesRegex(ValueError,"extra"):p.verify(root)

    def test_inventory_rejects_forged_extra_file_even_with_rehashed_manifest(self):
        root, _, _ = self.build()
        extra = root / "metadata/undocumented.txt"
        extra.write_bytes(b"unexpected")
        manifest = json.loads((root / "manifest.json").read_bytes())
        manifest["files"]["metadata/undocumented.txt"] = {
            "sha256": p.sha(extra.read_bytes()), "bytes": extra.stat().st_size}
        manifest.pop("package_root_sha256")
        manifest["package_root_sha256"] = p.sha(p.canonical(manifest))
        (root / "manifest.json").write_bytes(p.canonical(manifest) + b"\n")
        with self.assertRaisesRegex(ValueError, "unexpected evidence file"):
            p.verify(root)

    def test_requests_metadata_must_match_manifest(self):
        root, _, _ = self.build()
        path = root / "metadata/requests.json"
        path.write_bytes(b"[]")
        manifest = json.loads((root / "manifest.json").read_bytes())
        manifest["files"]["metadata/requests.json"] = {
            "sha256": p.sha(path.read_bytes()), "bytes": len(path.read_bytes())}
        manifest.pop("package_root_sha256")
        manifest["package_root_sha256"] = p.sha(p.canonical(manifest))
        (root / "manifest.json").write_bytes(p.canonical(manifest) + b"\n")
        with self.assertRaisesRegex(ValueError, "request metadata drift"):
            p.verify(root)

    def test_count_mismatch_fail_closed_with_incomplete(self):
        client=FakeClient([response(3),response(2,["1","2"])])
        with self.assertRaisesRegex(ValueError,"count mismatch"):
            p.collect(SPEC,"r-"+"1"*32,self.path/"package",client)
        self.assertEqual(json.loads((self.path/"package/manifest.json").read_bytes())["status"],"incomplete")
        with self.assertRaisesRegex(ValueError,"status mismatch"):p.verify(self.path/"package")

    def test_10k_guard_on_single_day(self):
        single=dict(SPEC,date_start="2026-01-01",date_end="2026-01-01")
        client=FakeClient([response(10000),response(10000)])
        with self.assertRaisesRegex(ValueError,"unsplittable"):
            p.collect(single,"r-"+"1"*32,self.path/"package",client)

    def test_deterministic_bisection(self):
        a,b=p.plan_spans(dt.date(2026,1,1),dt.date(2026,1,31))
        self.assertEqual(a,(dt.date(2026,1,1),dt.date(2026,1,16)))
        self.assertEqual(b,(dt.date(2026,1,17),dt.date(2026,1,31)))

    def test_reconciliation_missing_date_fails(self):
        spec=dict(SPEC,date_start="2026-01-01",date_end="2026-01-02")
        client=FakeClient([response(10000),response(2),response(2,["1","2"]),
                           response(2),response(2,["3","4"])])
        with self.assertRaisesRegex(ValueError,"union / source count mismatch"):
            p.collect(spec,"r-"+"1"*32,self.path/"package",client)

    def test_empty_result_is_final(self):
        client=FakeClient([response(0),response(0)])
        result=p.collect(SPEC,"r-"+"1"*32,self.path/"package",client)
        self.assertEqual(result["counts"], {"Q0":0})

    def test_long_query_is_post_timeout_and_redacted(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args): pass
            def read(self):return response(0)
        reqs=[]
        def opener(r,timeout):
            reqs.append((r,timeout))
            return Response()
        client=p.Client("tool","x@example.org",api_key="SECRET-KEY",opener=opener,sleep=lambda _:None)
        raw,_=client.esearch("x"*20000,0)
        self.assertEqual(raw,response(0))
        self.assertEqual(reqs[0][0].get_method(),"POST")
        self.assertEqual(reqs[0][1],35)
        self.assertIn(b"SECRET-KEY",reqs[0][0].data)
        self.assertNotIn("SECRET-KEY",reqs[0][0].full_url)

    def test_rate_limit_and_retry(self):
        calls=[]; sleeps=[]; clock=[1.0]
        class Resp:
            def __enter__(self):return self
            def __exit__(self,*a):return None
            def read(self):return response(1,["1"])
        def opener(req,timeout):
            calls.append(req)
            if len(calls)==1:raise p.error.HTTPError("url",429,"limited",{},None)
            return Resp()
        def sleep(v):sleeps.append(v);clock[0]+=v
        c=p.Client("tool","x@example.org",opener=opener,sleep=sleep,clock=lambda:clock[0])
        c.esearch("q",1)
        self.assertEqual(len(calls),2)
        self.assertGreaterEqual(sum(sleeps),1.0)
        self.assertTrue(any(x>=0.36 for x in sleeps))

    def test_package_limit_and_forbidden_paths(self):
        root,_,_=self.build()
        with mock.patch.object(p,"MAX_PACKAGE",1):
            with self.assertRaisesRegex(ValueError,"50 MiB"):p.verify(root)
        for path in ("../evil","/tmp/evil"):
            with self.assertRaises(ValueError):p.strict_path(root,path)
        with self.assertRaises(ValueError):p.validate_repository("Dr-snai1/Pro_Adherence")
        with self.assertRaises(ValueError):p.safe_id("../bad")

    def test_final_overwrite_rejected(self):
        root,_,_=self.build()
        with self.assertRaises(FileExistsError):p.collect(SPEC,"r-"+"1"*32,root,FakeClient([]))

    def test_local_git_write_fresh_readback_and_backup(self):
        if not shutil_which_git():self.skipTest("git is not installed")
        root,info,_=self.build()
        bare=self.path/"private.git"
        subprocess.run(["git","init","--bare","-b","main",str(bare)],check=True,stdout=subprocess.DEVNULL)
        with mock.patch.object(p,"validate_repository",return_value=str(bare)):
            sha,path,info=p.git_write(root,"Dr-snai1/Pro_Adherence-research-evidence")
            self.assertEqual(path,"pubmed/TASK-0004/r-"+"1"*32)
            fresh,src=p.clone_readback("Dr-snai1/Pro_Adherence-research-evidence",sha,"TASK-0004","r-"+"1"*32,
                                       target=self.path/"independent")
            self.assertEqual(fresh["root_hash"],info["root_hash"])
            backed=p.backup("Dr-snai1/Pro_Adherence-research-evidence",sha,"TASK-0004","r-"+"1"*32,self.path/"local-research")
            self.assertEqual(backed["root_hash"],info["root_hash"])
            with self.assertRaises(FileExistsError):p.git_write(root,"Dr-snai1/Pro_Adherence-research-evidence")


def shutil_which_git():
    import shutil
    return shutil.which("git")


if __name__ == "__main__": unittest.main()

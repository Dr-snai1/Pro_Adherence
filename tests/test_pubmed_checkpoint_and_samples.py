"""Independent failure injection: recovered partition, private checkpoint and sample XML."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from pro_adherence import pubmed_evidence as p

SPEC = {"schema":"pubmed-run-spec/v1","task_id":"TASK-0004","query_artifact":"frozen-artifact-v1",
        "queries":{"D_only":"adherence[tiab]"},"operation":"esearch-pmids",
        "partition_policy":p.PARTITION_POLICY,"date_start":"2026-01-01","date_end":"2026-01-02",
        "ncbi_config_refs":["NCBI_TOOL","NCBI_EMAIL","NCBI_API_KEY(optional)"]}


def result(n, ids=()):
    return json.dumps({"esearchresult":{"count":str(n),"idlist":list(ids),
                       "querytranslation":"frozen", "warninglist":{}}}).encode()

class Fake:
    def __init__(self, items):
        self.items=iter(items);self.queries=[]
    def esearch(self,query,retmax):
        self.queries.append((query,retmax))
        value = next(self.items)
        if isinstance(value, BaseException):
            raise value
        return value,{"endpoint":p.ENDPOINT,"method":"POST","utc":"2026-10-11T00:00:00Z","retmax":retmax}

class ResumeAndSamples(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.patch=mock.patch.dict(os.environ,{"PUBMED_CODE_COMMIT":"a"*40,"PUBMED_RUNTIME":"python-3.13.16",
                                     "NCBI_TOOL":"fixture","NCBI_EMAIL":"fixture@example.org"})
        self.patch.start();self.addCleanup(self.patch.stop)

    def incomplete(self):
        root=self.base/'p'
        fake=Fake([result(10000),result(10000),result(2),result(2,['1','2']),RuntimeError("network interrupted")])
        with self.assertRaisesRegex(RuntimeError,'interrupted'):
            p.collect(SPEC,'r-'+'2'*32,root,fake,timestamp='2026-10-11T00:00:00Z')
        proof=p.verify(root,require_final=False)
        self.assertEqual(proof['status'],'incomplete')
        self.assertEqual(len(json.loads((root/'manifest.json').read_bytes())['partitions']),1)
        return root

    def test_resume_reuses_verified_ids_and_completes(self):
        root=self.incomplete()
        previous=(root/'pmids/D_only/leaves/00000.txt').read_bytes()
        # Resume continues exact deterministic frontier; completed count/ids are reused.
        tail=[str(i) for i in range(3,10001)]
        fake=Fake([result(9998),result(9998,tail)])
        proof=p.collect(SPEC,'r-'+'2'*32,root,fake,resume=True)
        self.assertEqual(proof['counts'],{'D_only':10000})
        self.assertEqual((root/'pmids/D_only/leaves/00000.txt').read_bytes(),previous)
        self.assertEqual(len(fake.queries),2)
        self.assertEqual(p.verify(root)['root_hash'],proof['root_hash'])
        with self.assertRaises(FileExistsError):p.collect(SPEC,'r-'+'2'*32,root,Fake([]))

    def test_checkpoint_file_tamper_caught_before_network(self):
        root=self.incomplete();(root/'pmids/D_only/leaves/00000.txt').write_text('invalid\n')
        fake=Fake([])
        with self.assertRaisesRegex(ValueError,'hash'):
            p.collect(SPEC,'r-'+'2'*32,root,fake,resume=True)
        self.assertEqual(fake.queries,[])

    def test_wrong_execution_identity_rejected(self):
        root=self.incomplete();changed=dict(SPEC,query_artifact='other')
        with self.assertRaisesRegex(ValueError,'identity'):
            p.collect(changed,'r-'+'2'*32,root,Fake([]),resume=True)

    def test_incomplete_durable_git_commit_and_fresh_clone(self):
        root=self.incomplete();bare=self.base/'private.git'
        subprocess.run(['git','init','--bare','-b','main',str(bare)],check=True,stdout=subprocess.DEVNULL)
        with mock.patch.object(p,'validate_repository',return_value=str(bare)):
            first,rel,proof=p.git_write(root,'Dr-snai1/Pro_Adherence-research-evidence')
            self.assertEqual(proof['status'],'incomplete')
            with self.assertRaisesRegex(ValueError,'schema/status mismatch'):
                p.clone_readback('Dr-snai1/Pro_Adherence-research-evidence',first,'TASK-0004','r-'+'2'*32)
            prepared=self.base/'copied'
            restored=p.prepare_resume('Dr-snai1/Pro_Adherence-research-evidence', 'TASK-0004','r-'+'2'*32,prepared)
            self.assertEqual(restored['root_hash'],proof['root_hash'])
            tail=[str(i) for i in range(3,10001)]
            fake=Fake([result(9998),result(9998,tail)])
            completed=p.collect(SPEC,'r-'+'2'*32,prepared,fake,resume=True)
            second,_,_=p.git_write(prepared,'Dr-snai1/Pro_Adherence-research-evidence')
            self.assertNotEqual(first,second)
            fresh,_=p.clone_readback('Dr-snai1/Pro_Adherence-research-evidence',second,'TASK-0004','r-'+'2'*32,
                                     target=self.base/'fresh-final')
            self.assertEqual(fresh['root_hash'],completed['root_hash'])
            with self.assertRaises(FileExistsError):p.git_write(prepared,'Dr-snai1/Pro_Adherence-research-evidence')

    def test_resume_finishes_sample_after_efetch_failure(self):
        spec=dict(SPEC, sample_policy={"D_only": {"size":2,"sha256_prefix":"fixed|D_only|"}})
        fake=Fake([result(2),result(2,["1","2"])])
        def interrupted(_):
            raise RuntimeError("simulated EFetch outage")
        fake.efetch=interrupted
        root=self.base/"sample-outage"
        with self.assertRaisesRegex(RuntimeError,"outage"):
            p.collect(spec,"r-"+"2"*32,root,fake,timestamp="2026-10-11T00:00:00Z")
        interrupted_proof=p.verify(root,require_final=False)
        self.assertEqual(interrupted_proof["status"],"incomplete")
        self.assertEqual(interrupted_proof["counts"],{"D_only":2})
        self.assertFalse((root/"samples/D_only/pmids.txt").exists())
        fresh=Fake([])
        ordered=["1","2"]
        xml=b'<PubmedArticleSet>'+b''.join(f'<PubmedArticle><MedlineCitation><PMID>{x}</PMID></MedlineCitation></PubmedArticle>'.encode() for x in ordered)+b'</PubmedArticleSet>'
        def efetch(pmids):
            self.assertEqual(pmids, ordered)
            return xml, {"endpoint":p.EFETCH_ENDPOINT,"method":"POST","utc":"2026-10-11T01:00:00Z","retmax":2}
        fresh.efetch=efetch
        completed=p.collect(spec,"r-"+"2"*32,root,fresh,resume=True)
        self.assertEqual(completed["status"],"final")
        self.assertEqual(fresh.queries,[])
        self.assertEqual((root/"samples/D_only/pmids.txt").read_text().splitlines(),ordered)

    def test_zero_result_with_sample_does_not_call_efetch(self):
        spec=dict(SPEC,sample_policy={"D_only":{"size":10,"sha256_prefix":"fixed|D_only|"}})
        fake=Fake([result(0),result(0)])
        def forbidden(_):
            self.fail("EFetch should not be called on an empty PMID set")
        fake.efetch=forbidden
        root=self.base/"zero-sample"
        self.assertEqual(p.collect(spec,"r-"+"2"*32,root,fake)["status"],"final")
        self.assertEqual((root/"samples/D_only/pmids.txt").read_bytes(),b"")
        self.assertFalse((root/"raw/D_only/efetch/00001.xml").exists())

    def test_scientific_sample_is_frozen_deterministic_and_xml_bounded(self):
        spec=dict(SPEC, sample_policy={'D_only': {'size':2,'sha256_prefix':'PUBMED_ADHERENCE_v0.1-candidate_2026-10-09|D_only|'}})
        spec['date_start']='2026-01-01';spec['date_end']='2026-01-01'
        fake=Fake([result(3),result(3,['7','5','2'])])
        chosen=sorted(['2','5','7'],key=lambda n:hashlib.sha256((spec['sample_policy']['D_only']['sha256_prefix']+n).encode()).hexdigest())[:2]
        ordered=sorted(chosen,key=int)
        xml=b'<PubmedArticleSet>'+b''.join(f'<PubmedArticle><MedlineCitation><PMID>{x}</PMID></MedlineCitation></PubmedArticle>'.encode() for x in ordered)+b'</PubmedArticleSet>'
        def efetch(pmids):
            self.assertEqual(pmids,ordered)
            return xml, {'endpoint':p.EFETCH_ENDPOINT,'method':'POST','utc':'2026-10-11T00:00:00Z','retmax':2}
        fake.efetch=efetch
        root=self.base/'sample'
        proof=p.collect(spec,'r-'+'2'*32,root,fake,timestamp='2026-10-11T00:00:00Z')
        self.assertEqual(proof['status'],'final')
        self.assertEqual((root/'samples/D_only/pmids.txt').read_text().splitlines(),ordered)
        (root/'raw/D_only/efetch/00001.xml').write_bytes(b'<PubmedArticleSet/>')
        with self.assertRaisesRegex(ValueError,'hash'):p.verify(root)


    def test_single_selected_query_150_sample_and_book(self):
        spec = dict(SPEC, sample_policy={"D_only": {
            "size": 150, "sha256_prefix": "Pro_Adherence|V04_S0|2026-10-19|"}})
        spec_path = self.base / "selected.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        parsed, run_id = p.read_spec(
            spec_path, mode="full", code_commit="a" * 40,
            runtime="python-3.13.16")
        self.assertEqual(parsed["sample_policy"]["D_only"]["size"], 150)
        self.assertTrue(run_id.startswith("r-"))
        ids = [str(i) for i in range(1, 151)]
        chosen = p.selected_pmids(parsed, "D_only", ids)
        self.assertEqual(chosen, ids)
        xml = "<PubmedArticleSet>"
        for value in ids:
            if value == "40":
                xml += f"<PubmedBookArticle><BookDocument><PMID>{value}</PMID></BookDocument></PubmedBookArticle>"
            else:
                xml += f"<PubmedArticle><MedlineCitation><PMID>{value}</PMID></MedlineCitation></PubmedArticle>"
        xml += "</PubmedArticleSet>"
        p.checked_sample(xml.encode(), chosen)
        with self.assertRaisesRegex(ValueError, "EFetch PMID identity mismatch"):
            p.checked_sample(xml.replace("<PMID>40</PMID>", "<PMID>41</PMID>").encode(), chosen)
        spec["sample_policy"]["D_only"]["size"] = 151
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsafe sample size"):
            p.read_spec(spec_path, mode="full", code_commit="a"*40,
                        runtime="python-3.13.16")

if __name__=='__main__':unittest.main()

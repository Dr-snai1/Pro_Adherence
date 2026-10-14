"""D1 terminal PubMed semantic evidence; offline real-module and private-style Git fixtures."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pro_adherence import pubmed_evidence as p

SPEC = {"schema":"pubmed-run-spec/v1","task_id":"TASK-0004",
        "query_artifact":"frozen-artifact-v1","queries":{"A":"query-a"},
        "operation":"esearch-pmids","partition_policy":p.PARTITION_POLICY,
        "date_start":"2026-01-01","date_end":"2026-01-02",
        "ncbi_config_refs":["NCBI_TOOL","NCBI_EMAIL","NCBI_API_KEY(optional)"]}
REPO = "Dr-snai1/Pro_Adherence-research-evidence"

def raw(count, ids=()):
    return json.dumps({"esearchresult":{"count":str(count),"idlist":list(ids),
          "querytranslation":"fixture","warninglist":{}}}).encode()

class Client:
    def __init__(self, replies=()):
        self.replies=list(replies);self.calls=[]
    def esearch(self, query, retmax):
        self.calls.append((query,retmax))
        if not self.replies: raise AssertionError("unexpected network")
        reply=self.replies.pop(0)
        if isinstance(reply,BaseException):raise reply
        return reply,{"endpoint":p.ENDPOINT,"method":"POST",
                      "utc":"2026-10-13T10:00:00Z","retmax":retmax}
    def efetch(self, pmids):raise AssertionError("no sample allowed")

class TerminalTests(unittest.TestCase):
    RID="r-"+"d"*32
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)
        env=mock.patch.dict(os.environ,{"PUBMED_CODE_COMMIT":"a"*40,
              "PUBMED_RUNTIME":"python-3.13.16","NCBI_TOOL":"fixture",
              "NCBI_EMAIL":"fixture@example.org"})
        env.start();self.addCleanup(env.stop)
    def bare(self, name):
        path=self.base/(name+".git")
        subprocess.run(["git","init","--bare","-b","main",str(path)],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return path
    def failure(self, name, responses, spec=None):
        root=self.base/name;client=Client(responses)
        with self.assertRaises((ValueError,RuntimeError)):
            p.collect(spec or SPEC,self.RID,root,client)
        m=json.loads((root/"manifest.json").read_bytes())
        return root,client,m
    def terminal(self, reason, name):
        spec=copy.deepcopy(SPEC)
        if reason=="unsplittable_single_day_partition":
            spec["date_end"]=spec["date_start"]
            responses=[raw(10000),raw(10000)]
        elif reason=="source_count_mismatch":
            responses=[raw(10000),raw(10000),raw(1),raw(1,["1"]),
                       raw(1),raw(1,["2"])]
        else:raise AssertionError(reason)
        root,client,m=self.failure(name,responses,spec)
        self.assertEqual(m["status"],"incomplete")
        self.assertEqual(m["query_states"],{"A":"failed_terminal"})
        self.assertEqual(m["failure"],{"query_id":"A","stage":"search",
             "exception":"ValueError","disposition":"terminal","reason_code":reason})
        result=p.verify(root,require_final=False)
        self.assertEqual(result["failure_disposition"],"terminal")
        self.assertEqual(result["failure_reason_code"],reason)
        with self.assertRaises(ValueError):p.verify(root)
        self.assertFalse((root/p.union_path("A")).exists())
        return root,client,spec
    @staticmethod
    def rehash(root,m):
        (root/"metadata/requests.json").write_bytes(p.canonical(m["requests"]))
        m["files"]={f.relative_to(root).as_posix():
            {"sha256":p.sha(f.read_bytes()),"bytes":f.stat().st_size}
            for f in root.rglob("*") if f.is_file() and f.name!="manifest.json"}
        m.pop("package_root_sha256",None)
        m["package_root_sha256"]=p.sha(p.canonical(m))
        (root/"manifest.json").write_bytes(p.canonical(m)+b"\n")
    def durable(self,root,reason):
        bare=self.bare(reason)
        with mock.patch.object(p,"validate_repository",return_value=str(bare)):
            commit,_,proof=p.git_write(root,REPO)
            self.assertEqual(proof["failure_disposition"],"terminal")
            exact,copyroot=p.clone_readback(REPO,commit,"TASK-0004",self.RID,
                             target=self.base/(reason+"-readback"),require_final=False)
            self.assertEqual(exact["root_hash"],proof["root_hash"])
            self.assertEqual(exact["failure_reason_code"],reason)
            self.assertEqual(p.verify(copyroot,require_final=False),exact)
            with self.assertRaisesRegex(ValueError,"schema/status"):
                p.clone_readback(REPO,commit,"TASK-0004",self.RID,
                                 target=self.base/(reason+"-strict"))
            with self.assertRaisesRegex(ValueError,"terminal.*not resumable"):
                p.prepare_resume(REPO,"TASK-0004",self.RID,self.base/(reason+"-prepared"))
        return bare
    def no_resume(self,root,spec):
        client=Client()
        with self.assertRaisesRegex(ValueError,"terminal.*not resumable"):
            p.collect(spec,self.RID,root,client,resume=True)
        self.assertEqual(client.calls,[])
    def test_unsplittable_single_day_durable_git_readback_nonresume(self):
        root,client,spec=self.terminal("unsplittable_single_day_partition","day")
        self.assertEqual([x[1] for x in client.calls],[0,0])
        self.assertEqual(list((root/"raw/A/esearch").glob("*-ids.json")),[])
        self.durable(root,"unsplittable_single_day_partition")
        self.no_resume(root,spec)
    def test_completed_frontier_source_mismatch_durable(self):
        root,client,spec=self.terminal("source_count_mismatch","mismatch")
        self.assertEqual([x[1] for x in client.calls],[0,0,0,1,0,1])
        self.assertEqual(len(json.loads((root/"partitions/plan.json").read_bytes())),2)
        self.durable(root,"source_count_mismatch");self.no_resume(root,spec)
    def test_cross_leaf_overlap_source_mismatch_durable(self):
        responses=[raw(10000),raw(10000),raw(1),raw(1,["1"]),
                   raw(1),raw(1,["1"])]
        root,_,m=self.failure("duplicate",responses)
        self.assertEqual(m["failure"]["reason_code"],"source_count_mismatch")
        leaves=json.loads((root/"partitions/plan.json").read_bytes())
        self.assertEqual([(root/x["pmid_file"]).read_text() for x in leaves],["1\n","1\n"])
        self.assertEqual(p.verify(root,require_final=False)["failure_reason_code"],"source_count_mismatch")
        self.durable(root,"source_count_mismatch");self.no_resume(root,SPEC)
    def test_forged_terminal_on_pending_evidence(self):
        root,_,m=self.failure("pending",[RuntimeError("outage")])
        self.assertEqual(p.verify(root,require_final=False)["failure_disposition"],"resumable")
        m["query_states"]["A"]="failed_terminal"
        m["failure"].update({"disposition":"terminal",
           "reason_code":"unsplittable_single_day_partition","exception":"ValueError"})
        self.rehash(root,m)
        with self.assertRaisesRegex(ValueError,"terminal"):
            p.verify(root,require_final=False)
    def test_forged_resumable_on_terminal_evidence(self):
        root,_,spec=self.terminal("unsplittable_single_day_partition","fake-resume")
        m=json.loads((root/"manifest.json").read_bytes())
        m["query_states"]["A"]="failed_checkpointable"
        m["failure"].update({"disposition":"resumable","reason_code":"search_pending"})
        self.rehash(root,m)
        with self.assertRaises(ValueError):p.verify(root,require_final=False)
        silent=Client()
        with self.assertRaises(ValueError):p.collect(spec,self.RID,root,silent,resume=True)
        self.assertEqual(silent.calls,[])
    def test_resumable_rejected_count_ids_malformed(self):
        cases=[("malformed",[b"{broken"],[raw(0),raw(0)]),
               ("invalid-count",[raw(0,["1"])],[raw(0),raw(0)]),
               ("invalid-ids",[raw(0),raw(1,["1"])],[raw(0)])]
        for name,responses,retry in cases:
            with self.subTest(name=name):
                root,_,m=self.failure(name,responses)
                self.assertEqual(m["query_states"]["A"],"failed_checkpointable")
                self.assertEqual(m["failure"]["reason_code"],"search_pending")
                self.assertEqual(p.verify(root,require_final=False)["status"],"incomplete")
                bare=self.bare(name)
                with mock.patch.object(p,"validate_repository",return_value=str(bare)):
                    p.git_write(root,REPO)
                    target=self.base/(name+"-recovered")
                    self.assertEqual(p.prepare_resume(REPO,"TASK-0004",self.RID,target)["status"],"incomplete")
                resumed=Client(retry)
                self.assertEqual(p.collect(SPEC,self.RID,target,resumed,resume=True)["status"],"final")
                self.assertTrue(resumed.calls)
    def test_terminal_run_id_immutable(self):
        root,_,_=self.terminal("source_count_mismatch","immutable")
        bare=self.bare("immutable")
        with mock.patch.object(p,"validate_repository",return_value=str(bare)):
            p.git_write(root,REPO)
            final=self.base/"legitimate-final"
            p.collect(SPEC,self.RID,final,Client([raw(0),raw(0)]))
            with self.assertRaisesRegex(FileExistsError,"terminal.*immutable"):
                p.git_write(final,REPO)
            with self.assertRaises(FileExistsError):p.git_write(root,REPO)
    def test_wrong_reason_and_corrupt_leaf_rejected(self):
        root,_,_=self.terminal("source_count_mismatch","wrong")
        m=json.loads((root/"manifest.json").read_bytes())
        m["failure"]["reason_code"]="cross_leaf_duplicate";self.rehash(root,m)
        with self.assertRaises(ValueError):p.verify(root,require_final=False)
        other,_,_=self.failure("corrupt",[raw(10000),raw(10000),
             raw(1),raw(1,["1"]),raw(1),raw(1,["1"])])
        m=json.loads((other/"manifest.json").read_bytes())
        (other/m["partitions"][0]["pmid_file"]).write_text("999\n")
        self.rehash(other,m)
        with self.assertRaises(ValueError):p.verify(other,require_final=False)
    def test_final_readback_default_remains_strict(self):
        root=self.base/"success"
        p.collect(SPEC,self.RID,root,Client([raw(0),raw(0)]))
        bare=self.bare("success")
        with mock.patch.object(p,"validate_repository",return_value=str(bare)):
            commit,_,proof=p.git_write(root,REPO)
            verified,_=p.clone_readback(REPO,commit,"TASK-0004",self.RID,
                                        target=self.base/"strict-success")
            self.assertEqual(verified["root_hash"],proof["root_hash"])
    def test_workflow_readback_before_failure_message(self):
        text=(Path(__file__).resolve().parents[1]/
              ".github/workflows/pubmed-evidence-manual.yml").read_text()
        self.assertIn("workflow_dispatch:",text)
        self.assertIn("permissions:\n  contents: read",text)
        self.assertIn("secrets.RESEARCH_EVIDENCE_WRITE_SSH_KEY",text)
        self.assertIn("secrets.RESEARCH_EVIDENCE_READ_SSH_KEY",text)
        verifier=text.split("  independent-readback:",1)[1]
        self.assertIn("--allow-incomplete",verifier)
        self.assertLess(verifier.index("readback_flag"),
                        verifier.index("Durable terminal failure evidence verified"))
        self.assertLess(verifier.index("independent failure disposition/status mismatch"),
                        verifier.index("Durable terminal failure evidence verified"))
        self.assertIn("Durable resumable incomplete checkpoint verified; re-run with matching resume_id.",verifier)
        self.assertNotIn("Durable incomplete checkpoint saved; re-run with matching resume_id.",text)
        self.assertNotIn("Fail if source retrieval remained incomplete",text)

if __name__=="__main__":unittest.main()

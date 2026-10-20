"""Evaluate user-authored V05 phrase query on frozen 500R/369N PMID reference.

The source query is read byte-for-byte from its Drive-sourced TXT snapshot.
Old V04 membership comes from the previously independently validated CSV.
No query optimization or modifications are performed.
"""
import collections,csv,datetime,hashlib,json,re,time
from pathlib import Path
from query_probe_precision_20261019 import api

ROOT=Path("research/validation_candidate_set_20261019")
V05_FILE=Path("research/PubMed_V05_PHRASE_CANDIDATE_20261020.txt")
REF=ROOT/"reference_FINAL_v2_R500_N369.csv"
PREVIOUS=ROOT/"reference_FINAL_v2_query_2x2.csv"
PREVIOUS_METRICS=ROOT/"reference_FINAL_v2_query_2x2.json"
OUT=ROOT/"reference_FINAL_v2_V05_PHRASE_2x2.csv"
RESULT=ROOT/"reference_FINAL_v2_V05_PHRASE_2x2.json"

query=V05_FILE.read_text(encoding="utf-8")
assert query.startswith("(\n"),"Input begins unexpectedly"
assert query.strip().endswith('AND "journal article"[pt]'),"Expected publication filter absent"
assert query.count('english[la]')==1 and query.count('"journal article"[pt]')==1
depth=0;quoted=False
for char in query:
    if char=='"':quoted=not quoted
    if not quoted:
        if char=="(":depth+=1
        if char==")":depth-=1
        assert depth>=0,"Parenthesis closed prematurely"
assert depth==0 and not quoted,"Unbalanced input"
query_sha256=hashlib.sha256(query.encode()).hexdigest()
rows=list(csv.DictReader(REF.open(encoding="utf-8",newline="")))
ids=[x["pmid"] for x in rows]
truth={x["pmid"]:x["label"] for x in rows}
assert len(ids)==len(truth)==869
assert collections.Counter(truth.values())=={"R":500,"N":369}
old_records=list(csv.DictReader(PREVIOUS.open(encoding="utf-8",newline="")))
prior={x["pmid"]:x for x in old_records}
assert len(prior)==869 and set(prior)==set(truth)
for p,v in truth.items():assert prior[p]["reference_label"]==v
prior_metrics=json.loads(PREVIOUS_METRICS.read_text(encoding="utf-8"))["metrics"]

warnings=set()
def esearch(term,retmax=0):
    last_exc=None
    for attempt in range(4):
        try:
            raw=api("esearch.fcgi",{"db":"pubmed","term":term,"retmode":"json","retmax":retmax})
            dat=json.loads(raw)
            v=dat.get("esearchresult",{})
            if "count" not in v:raise RuntimeError("Missing ESearch count "+json.dumps(dat)[:850])
            for k,values in v.get("warninglist",{}).items():
                for x in values or []:warnings.add(k+": "+x)
            if int(v["count"])<0:raise RuntimeError("Negative ESearch count")
            time.sleep(.44)
            return v
        except Exception as e:
            last_exc=e
            print("PUBMED_RETRY",attempt,str(e)[:230],flush=True)
            time.sleep(2.5*(attempt+1))
    raise last_exc

# Full term diagnostic, followed by exact PMID constrained searches.
whole=esearch(query,0)
print("V05_TOTAL_PUBMED_RESULTS",whole["count"],"WARNINGLIST",whole.get("warninglist"),flush=True)

def lookup(records,block_size):
    matched=set()
    for off in range(0,len(records),block_size):
        block=records[off:off+block_size]
        clause="("+query+") AND ("+" OR ".join(p+"[uid]" for p in block)+")"
        res=esearch(clause,len(block)+5)
        found=set(res.get("idlist") or [])
        assert len(found)==int(res["count"]),(off,len(found),res["count"])
        assert found <= set(block),("ESearch returned unexpected PMIDs",found-set(block))
        matched.update(found)
    return matched

primary=lookup(ids,35)
print("V05_PRIMARY",len(primary),"R",sum(truth[p]=="R" for p in primary),"N",sum(truth[p]=="N" for p in primary),flush=True)

# Independent re-evaluation using unrelated shuffling, label-stratification,
# and different chunk boundaries (47 vs 35).
salt=hashlib.sha256(b"V05_PubMed_phrase_candidate_20261020_validation").hexdigest()
second=set()
for label in ("R","N"):
    lst=sorted((p for p in ids if truth[p]==label),key=lambda p:hashlib.sha256((salt+"|"+p).encode()).hexdigest())
    hit=lookup(lst,47)
    assert hit=={p for p in primary if truth[p]==label},"Independent matching conflict "+label
    second.update(hit)
assert second==primary,"Full primary vs independent result mismatch"
print("V05_INDEPENDENT_REPARTITION_PASSED",len(second),flush=True)

tp=sum(truth[p]=="R" for p in primary)
fp=sum(truth[p]=="N" for p in primary)
fn=500-tp
tn=369-fp
assert all(n>=0 for n in (tp,fp,fn,tn))
assert tp+fn==500 and tn+fp==369
m={
    "TP":tp,"FN":fn,"FP":fp,"TN":tn,
    "sensitivity":tp/500,"specificity":tn/369,
    "TP_share_R":tp/500,"FN_share_R":fn/500,
    "FP_share_N":fp/369,"TN_share_N":tn/369,
    "retrieved_reference_total":tp+fp,
    "missed_reference_total":fn+tn
}
with OUT.open("w",newline="",encoding="utf-8") as f:
    columns=["pmid","reference_label","V04_S0","V04_S0_plus_methods_v2","V05_PHRASE"]
    w=csv.DictWriter(f,fieldnames=columns)
    w.writeheader()
    for p in ids:
        w.writerow({
            "pmid":p,"reference_label":truth[p],
            "V04_S0":prior[p]["V04_S0"],
            "V04_S0_plus_methods_v2":prior[p]["V04_S0_plus_methods_v2"],
            "V05_PHRASE":int(p in primary)
        })
# Recheck by independently recomputing 2x2 from persisted 869 rows, 
# then cross-check against earlier V04 metrics and selection diffs.
with OUT.open("r",newline="",encoding="utf-8") as f:
    parsed=list(csv.DictReader(f))
assert len(parsed)==869
for key,metric in [("V05_PHRASE",m),("V04_S0",prior_metrics["V04_S0"]),("V04_S0_plus_methods_v2",prior_metrics["V04_S0_plus_methods_v2"])]:
    actual=collections.Counter((r["reference_label"],r[key]) for r in parsed)
    assert actual[("R","1")]==metric["TP"] and actual[("R","0")]==metric["FN"]
    assert actual[("N","1")]==metric["FP"] and actual[("N","0")]==metric["TN"]
add_r=[p for p in ids if truth[p]=="R" and p in primary and prior[p]["V04_S0"]=="0"]
lost_r=[p for p in ids if truth[p]=="R" and p not in primary and prior[p]["V04_S0"]=="1"]
add_n=[p for p in ids if truth[p]=="N" and p in primary and prior[p]["V04_S0"]=="0"]
lost_n=[p for p in ids if truth[p]=="N" and p not in primary and prior[p]["V04_S0"]=="1"]
result={
    "status":"VERIFIED_WITH_TWO_INDEPENDENT_PUBMED_QUERIES_AND_EXPORT_RECOUNT",
    "query_source":"Google Drive: PubMed_V05_PHRASE_CANDIDATE_20261020.txt",
    "query_source_url":"https://drive.google.com/file/d/1nd5TFn1JN32sNZLcQ3F07RlfUgWC2ME2/view?usp=drivesdk",
    "query_snapshot_file":str(V05_FILE),
    "query_source_sha256":query_sha256,
    "reference_file":str(REF),
    "reference_sha256":hashlib.sha256(REF.read_bytes()).hexdigest(),
    "population":{"R":500,"N":369},
    "v05_pubmed_total_count":int(whole["count"]),
    "v05_warninglist":whole.get("warninglist",{}),
    "all_warnings":sorted(warnings),
    "v05_metrics":m,
    "prior_verified_metrics":prior_metrics,
    "vs_V04_S0":{
        "additional_R":add_r,
        "missed_previous_R":lost_r,
        "additional_N":add_n,
        "avoided_previous_N":lost_n
    },
    "checks":[
        "Live NCBI ESearch POST for exact Drive-source V05 with frozen 869 PMID.",
        "Independent repeat using alternative 47-PMID blocks, deterministic shuffle and label partitions.",
        "Independent numeric recount of output CSV and agreement with the previous V04 comparator matrices.",
        "No modifications to accepted V04 or source V05 query."
    ],
    "interpretation":"Provisional (silver), nonrepresentative, query-sourced reference. Metrics describe within-set performance, not general PubMed sensitivity/specificity.",
    "tested_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()
}
RESULT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("V05_FINAL_2X2",json.dumps(m,ensure_ascii=False),flush=True)
print("DIFF_R",len(add_r),len(lost_r),"DIFF_N",len(add_n),len(lost_n),flush=True)
print("V05_WARNINGS",json.dumps(sorted(warnings),ensure_ascii=False),flush=True)

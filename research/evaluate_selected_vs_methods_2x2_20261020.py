"""Independent 2x2 evaluation of selected V04 and measurement-expanded candidate.

Research only; operational reference contains silver labels, not validated gold.
Source of PMIDs: frozen reference_FINAL_v2_R500_N369.csv.
No NOT or query modification; evaluate exact PubMed live matching per PMID.
"""
import collections,csv,datetime,hashlib,json,time
from pathlib import Path
from query_probe_precision_20261019 import api

ROOT=Path("research")
REF=ROOT/"validation_candidate_set_20261019/reference_FINAL_v2_R500_N369.csv"
MANIFEST=ROOT/"validation_candidate_set_20261019/reference_FINAL_v2_manifest.json"
BASE=Path("configs/pubmed/medication-adherence-SELECTED.v1.json")
NEW=ROOT/"pubmed_method_expansion_CANDIDATE_v2_20261020.json"
OUT=ROOT/"validation_candidate_set_20261019/reference_FINAL_v2_query_2x2.csv"
RESULT=ROOT/"validation_candidate_set_20261019/reference_FINAL_v2_query_2x2.json"

rows=list(csv.DictReader(REF.open(encoding="utf-8",newline="")))
info=json.loads(MANIFEST.read_text(encoding="utf-8"))
a=json.loads(BASE.read_text(encoding="utf-8"))["queries"]["V04_S0"]
b=json.loads(NEW.read_text(encoding="utf-8"))["query"]
ids=[r["pmid"] for r in rows]
true={r["pmid"]:r["label"] for r in rows}
assert len(rows)==len(ids)==len(true)==869
assert collections.Counter(true.values())=={"R":500,"N":369}
assert info["labels"]=={"R":500,"N":369}
assert a!=b
assert "NOT" not in a.upper().split() and "NOT" not in b.upper().split()
suffix=' AND (english[la] AND "journal article"[pt]))'
assert b.startswith(a[:-len(suffix)]) and b.endswith(suffix),"candidate changes selected backbone"

def esearch(term,retmax):
    for attempt in range(4):
        try:
            dat=json.loads(api("esearch.fcgi",{"db":"pubmed","term":term,"retmode":"json","retmax":retmax}))
            r=dat.get("esearchresult",{})
            if "count" not in r:raise RuntimeError(str(dat)[:800])
            if r.get("warninglist",{}).get("phrasesignored") or r.get("warninglist",{}).get("quotedphrasesnotfound"):
                raise RuntimeError("PubMed query warning: "+str(r["warninglist"]))
            time.sleep(.48)
            return r
        except Exception as ex:
            if attempt==3:raise
            print("RETRY",str(ex)[:300],flush=True)
            time.sleep(attempt*3+2)

def hits(q,ids,chunk_size=35):
    got=set()
    countsum=0
    for start in range(0,len(ids),chunk_size):
        batch=ids[start:start+chunk_size]
        term="("+q+") AND ("+" OR ".join(p+"[uid]" for p in batch)+")"
        x=esearch(term,len(batch)+3)
        found=set(x.get("idlist",[]))
        n=int(x["count"])
        assert n==len(found),("not enough ids",start,n,len(found))
        assert found<=set(batch),("unexpected PMID",start,found-set(batch))
        got.update(found)
        countsum+=n
    assert len(got)==countsum,(len(got),countsum)
    return got

# Primary evaluation: interleaved 35-PMID blocks across full reference.
matched={}
for name,q in [("V04_S0",a),("V04_S0_plus_methods_v2",b)]:
    match=hits(q,ids,35)
    matched[name]=match
    print("PRIMARY",name,"MATCH",len(match),"R",sum(true[p]=="R" for p in match),"N",sum(true[p]=="N" for p in match),flush=True)
assert matched["V04_S0"]<=matched["V04_S0_plus_methods_v2"]

# Independent validation: different ordering and different block boundaries,
# partitioned by actual relevance label instead of mixing R and N.
rng=hashlib.sha256(b"validation-2x2-2026-10-20").hexdigest()
for name,q in [("V04_S0",a),("V04_S0_plus_methods_v2",b)]:
    check=set()
    for classification in ("R","N"):
        group=[p for p in ids if true[p]==classification]
        # deterministic unrelated sort
        group.sort(key=lambda p:hashlib.sha256((rng+"|"+p).encode()).hexdigest())
        part=hits(q,group,47)
        check.update(part)
        assert part=={p for p in matched[name] if true[p]==classification},name+" "+classification
    assert check==matched[name],name
    print("INDEPENDENT_REPARTITION_PASS",name,"COUNT",len(check),flush=True)

def summarize(name,hit):
    tp=sum(true[p]=="R" for p in hit)
    fp=sum(true[p]=="N" for p in hit)
    fn=500-tp
    tn=369-fp
    assert all(x>=0 for x in (tp,fp,fn,tn))
    assert tp+fn==500 and fp+tn==369 and tp+fp==len(hit)
    return {
        "TP":tp,"FN":fn,"FP":fp,"TN":tn,
        "sensitivity":tp/500,"specificity":tn/369,
        "TP_share_R":tp/500,"FN_share_R":fn/500,
        "FP_share_N":fp/369,"TN_share_N":tn/369,
        "retrieved_reference_total":tp+fp,
        "missed_reference_total":fn+tn
    }
metrics={name:summarize(name,got) for name,got in matched.items()}
x=metrics["V04_S0"];y=metrics["V04_S0_plus_methods_v2"]
assert y["TP"]>=x["TP"] and y["FP"]>=x["FP"]
assert y["TN"]<=x["TN"] and y["FN"]<=x["FN"]
with OUT.open("w",encoding="utf-8",newline="") as f:
    fields=["pmid","reference_label","V04_S0","V04_S0_plus_methods_v2"]
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
    writer.writerows({
        "pmid":p,"reference_label":true[p],
        "V04_S0":int(p in matched["V04_S0"]),
        "V04_S0_plus_methods_v2":int(p in matched["V04_S0_plus_methods_v2"]),
    } for p in ids)
result={
    "status":"LIVE_QUERY_MATCH_VERIFIED_NOT_GOLD",
    "timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "reference_file":str(REF),
    "reference_sha256":hashlib.sha256(REF.read_bytes()).hexdigest(),
    "labels":"SILVER; 500 R and 369 N are heuristically screened rather than independently adjudicated gold",
    "base_sha256":hashlib.sha256(a.encode()).hexdigest(),
    "expanded_sha256":hashlib.sha256(b.encode()).hexdigest(),
    "metrics":metrics,
    "checks":[
        "Primary PMID-by-PMID ESearch in mixed 35-size windows.",
        "Independent ESearch in label-partitioned shuffled 47-size windows, exact hit-set equality.",
        "Row margins and reference membership, unique PMIDs, candidate superset and absence of excluded Ns."
    ],
    "interpretation_caveat":"Retrospective query-derived nonrepresentative silver corpus; sensitivity/specificity are sample-internal reference metrics, not general PubMed search sensitivity/specificity."
}
RESULT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
# Second numeric-only check recompute from exported matrix without using matched sets.
with OUT.open(newline="",encoding="utf-8") as f:
    rd=list(csv.DictReader(f))
assert len(rd)==869
for name,m in metrics.items():
    h=[r for r in rd if r[name]=="1"]
    assert sum(r["reference_label"]=="R" for r in h)==m["TP"]
    assert sum(r["reference_label"]=="N" for r in h)==m["FP"]
    assert sum(r["reference_label"]=="R" and r[name]=="0" for r in rd)==m["FN"]
    assert sum(r["reference_label"]=="N" and r[name]=="0" for r in rd)==m["TN"]
print("MATRICES_VALIDATED",json.dumps(metrics,ensure_ascii=False),flush=True)

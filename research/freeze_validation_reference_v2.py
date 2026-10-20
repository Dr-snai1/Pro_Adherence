"""Freeze reference evaluation set: remove 129 low-confidence Ns and two N errors.
No label laundering: final means frozen membership, NOT independently validated gold.
"""
from pathlib import Path
from collections import Counter
import csv,json,hashlib
root=Path("research/validation_candidate_set_20261019")
old=root/"silver_1000_labels.csv"
outfile=root/"reference_FINAL_v2_R500_N369.csv"
excluded_file=root/"reference_FINAL_v2_exclusions.csv"
manifest_file=root/"reference_FINAL_v2_manifest.json"
oldmanifest=root/"manifest.json"
with old.open(newline="",encoding="utf-8") as f:
 rd=csv.DictReader(f)
 cols=rd.fieldnames
 rows=list(rd)
assert len(rows)==1000,len(rows)
assert Counter(x["label"] for x in rows)=={"R":500,"N":500}
forced_U={"24702721":"patient_medication_taking_substantively_studied",
          "33464991":"medication_initiation_and_continuation_studied"}
excluded=[]
active=[]
for row in rows:
 reason=None
 if row["label"]=="N" and row["label_basis"]=="provisional_negative_other_topic_requires_expert_review":
  reason="low_confidence_negative_129"
 elif row["pmid"] in forced_U and row["label"]=="N":
  reason=forced_U[row["pmid"]]
 if reason:
  excluded.append({"pmid":row["pmid"],"original_label":row["label"],"reason":reason,"title":row["title"],"source_basis":row["label_basis"]})
 else:active.append(row)
assert len(excluded)==131
assert Counter(x["reason"] for x in excluded)["low_confidence_negative_129"]==129
count=Counter(x["label"] for x in active)
assert count=={"R":500,"N":369},count
assert len({r["pmid"] for r in active})==len(active)==869
assert all(r["label_basis"]!="provisional_negative_other_topic_requires_expert_review" for r in active)
assert not any(r["pmid"] in forced_U for r in active)
pos=set("9404746 12441805 17110087 22021483 23032359 23065532 25301330 26495883 28807035 29081045 29427293 31626087 31929426 33371973 35173501 35416595 37091492 38603915 38730371 39525610 41798698".split())
neg=set("1332520 2448571 2792052 2898461 3555041 7414106 8141977 8914177 9676753 9730424 9888412 10103334".split())
byid={r["pmid"]:r["label"] for r in active}
assert all(byid.get(p)=="R" for p in pos)
assert all(byid.get(p)=="N" for p in neg)
with outfile.open("w",newline="",encoding="utf-8") as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(active)
with excluded_file.open("w",newline="",encoding="utf-8") as f:
 keys=["pmid","original_label","reason","title","source_basis"];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(excluded)
record={
 "version":"2026-10-20-reference-FINAL-v2",
 "status":"FINAL_FROZEN_FOR_EXPLORATORY_QUERY_EVALUATION",
 "label_evidence_status":"heuristic_screened_silver_NOT_independently_adjudicated_gold",
 "source_file":"silver_1000_labels.csv",
 "source_version":"2026-10-19-silver-v1.1",
 "result_file":outfile.name,
 "total":len(active),"labels":dict(count),
 "excluded_total":len(excluded),
 "excluded_low_confidence_N":129,
 "excluded_prior_N_misclassification_or_high_risk":2,
 "excluded_pmids_extra":sorted(forced_U),
 "previous_sentinels":{"positive_count":len(pos),"negative_count":len(neg),"all_retained":True},
 "provenance":"PubMed prior query strata, rule evidence and independent title/abstract verification for removed misclassified/high-risk N",
 "use_limitation":"Frozen user-requested benchmark, not a scientifically validated adjudicated gold-standard; 500/369 balancedness differs, not a prevalence sample",
 "no_new_annotator_work_required":True,
 "public_abstracts_embedded":False,
}
manifest_file.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
oldm=json.loads(oldmanifest.read_text(encoding="utf-8"))
oldm["status"]="superseded"
oldm["superseded_by"]=outfile.name
oldm["superseded_on"]="2026-10-20"
oldm["reason"]="129 lower-confidence negatives and 2 additional likely-positive/borderline records excluded as user requested"
oldmanifest.write_text(json.dumps(oldm,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
readme=root/"README.md"
raw=readme.read_text(encoding="utf-8")
section="""
## Current evaluation reference: FINAL v2 (2026-10-20)
Primary active set is `reference_FINAL_v2_R500_N369.csv`, with exactly 500 R
and 369 N (869 unique PMIDs). Removed the 129 less-confident negatives,
plus two further incorrect/at-risk N (24702721, 33464991). Prior 1000-row
file remains as historical superseded evidence, NEVER use it as active set.
All 21 assistant-reviewed R and 12 user-reviewed N examples are retained.
Final means fixed operational selection; heuristically screened references
are NOT independently adjudicated gold labels. See v2 manifest.
"""
if "## Current evaluation reference: FINAL v2" not in raw:
 readme.write_text(raw+section,encoding="utf-8")
# Second independent roundtrip parse of both active dataset and manifest.
with outfile.open(newline="",encoding="utf-8") as f: reload=list(csv.DictReader(f))
m2=json.loads(manifest_file.read_text(encoding="utf-8"))
assert len(reload)==m2["total"]==869
assert Counter(r["label"] for r in reload)==Counter(m2["labels"])
assert len({r["pmid"] for r in reload})==869
print("FINAL_V2_COMPLETE",len(reload),m2["labels"],"EXCLUDED",len(excluded),"SENTINELS",len(pos),len(neg),flush=True)

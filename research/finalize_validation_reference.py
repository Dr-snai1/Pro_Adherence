"""Repair provenance-sensitive sentinel retention without refetching PubMed.
Labels are SILVER / provisional, not gold. Generated 1000-row corpus remains fixed size.
"""
import csv,json,re,hashlib
from pathlib import Path
from collections import Counter
ROOT=Path("research/validation_candidate_set_20261019")
FILE=ROOT/"silver_1000_labels.csv"
POS="9404746 12441805 17110087 22021483 23032359 23065532 25301330 26495883 28807035 29081045 29427293 31626087 31929426 33371973 35173501 35416595 37091492 38603915 38730371 39525610 41798698".split()
NEG="1332520 2448571 2792052 2898461 3555041 7414106 8141977 8914177 9676753 9730424 9888412 10103334".split()
with FILE.open(encoding="utf-8",newline="") as f:
 reader=csv.DictReader(f); cols=reader.fieldnames; original=list(reader)
assert len(original)==1000 and len({x["pmid"] for x in original})==1000
source={}
for path in sorted(ROOT.glob("all_candidates_part_*.csv")):
 with path.open(encoding="utf-8",newline="") as f:
  for r in csv.DictReader(f):
   if r["pmid"] in source: raise AssertionError("duplicate corpus source "+r["pmid"])
   source[r["pmid"]]=r
assert len(source)>4000
assert set(POS+NEG)<=set(source)
cur={x["pmid"]:x for x in original}
added=[]
for pmid in POS:
 r=dict(source[pmid])
 r["label"]="R"
 if pmid=="9404746":
  r["confidence"]="5"
  r["label_basis"]="human_preexisting_confirmed"
 else:
  r["confidence"]="3"
  r["label_basis"]="previous_expert_screen_not_human_confirmed"
 if pmid not in cur:
  cur[pmid]=r;added.append(pmid)
 else:
  cur[pmid].update(label=r["label"],confidence=r["confidence"],label_basis=r["label_basis"])
for pmid in NEG:
 assert pmid in cur and cur[pmid]["label"]=="N",pmid
positives=[r for r in cur.values() if r["label"]=="R"]
assert len(positives)==500+len(added)
# Remove only easy, non-sentinel title-based positives to preserve diverse challenge cases.
sent=set(POS)
removable=[r for r in positives if r["pmid"] not in sent]
removable.sort(key=lambda r:(
  1 if r["label_basis"]=="explicit_title_plus_patient_drug_adherence" else 0,
  1 if "H_titleonly" in r["sources"].split(";") else 0,
  hashlib.sha256(("reference-sentinel-replace-v1|"+r["pmid"]).encode()).hexdigest()
 ),reverse=True)
removed=[]
for r in removable[:len(added)]:
 cur.pop(r["pmid"]);removed.append(r["pmid"])
rows=sorted(cur.values(),key=lambda r:(r["label"],int(r["pmid"])))
counts=Counter(x["label"] for x in rows)
assert len(rows)==1000 and counts==Counter({"R":500,"N":500}),counts
assert all(set(POS+NEG)<=set(x["pmid"] for x in rows) for _ in [0])
assert all(set(r.keys())==set(cols) for r in rows)
assert all(re.fullmatch(r"\d+",r["pmid"]) for r in rows)
assert not any("abstract" in r and r.get("abstract","") for r in rows)
with FILE.open("w",encoding="utf-8",newline="") as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
manifest_path=ROOT/"manifest.json"
m=json.loads(manifest_path.read_text(encoding="utf-8"))
m["version"]="2026-10-19-silver-v1.1"
m["status"]="provisional_silver_not_gold"
m["sentinel_retention"]={
 "all_21_previous_expert_relevant_in_positive_500":True,
 "all_12_previous_user_irrelevant_in_negative_500":True,
 "previous_expert_label_not_human_confirmation":True,
 "added_expert_positive_pmids":added,
 "removed_easy_positive_pmids":removed,
 "postprocessing_script":"research/finalize_validation_reference.py",
 "selection_note":"Forced inclusion of all prior known positive and negative sentinels. Expert positive classifications except 9404746 need independent confirmation.",
 }
manifest_path.write_text(json.dumps(m,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
readme=ROOT/"README.md"
t=readme.read_text(encoding="utf-8")
note="\n## Reference v1.1 retention guarantee\nAll 21 earlier assistant-reviewed positive examples are present as R (one user-confirmed); all 12 earlier user-reviewed N examples are present as N. This is NOT independent expert consensus. See manifest.json and label_basis for provenance. The accepted PubMed search query is unchanged.\n"
if "## Reference v1.1 retention guarantee" not in t:
 readme.write_text(t+note,encoding="utf-8")
print("REFERENCE_SENTINELS_OK",len(rows),"R",counts["R"],"N",counts["N"],"added",len(added),"replaced",len(removed),"corpus",len(source),flush=True)
print("SENTINEL_POSITIVE_IDS",",".join(POS),flush=True)
print("SENTINEL_NEGATIVE_IDS",",".join(NEG),flush=True)

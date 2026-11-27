"""Assemble restricted temporal and WoS-restoration packages; verify member bytes."""
import gzip,json,hashlib,sys,zipfile
from pathlib import Path
import numpy as np
from stage3_temporal_fixed import load,yearrows,sha

def pack(path,members,scope):
 manifest={'schema':'stage3-private-evidence-package/v1','scope':scope,'members':{name:{'bytes':p.stat().st_size,'sha256':sha(p)} for name,p in members.items()}}
 with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for n,p in members.items():z.write(p,n)
  z.writestr('archive_manifest.json',json.dumps(manifest,indent=2,ensure_ascii=False))
 with zipfile.ZipFile(path) as z:
  assert z.testzip() is None and set(z.namelist())==set(members)|{'archive_manifest.json'};assert all(hashlib.sha256(z.read(n)).hexdigest()==m['sha256'] and len(z.read(n))==m['bytes'] for n,m in manifest['members'].items())
 path.chmod(0o600);print(path.name,path.stat().st_size,sha(path),flush=True)

def run(root,d):
 R=yearrows(root,d);p,_,_=load(root,R,False,False);delta=list(map(json.loads,gzip.open(d/'corrected_input_changes.private.jsonl.gz','rt')));changed=np.zeros(len(R),bool)
 for x in delta:
  assert x['article_id']==R[x['row_index']]['article_id']
  if x['text_changed']:changed[x['row_index']]=True
 impact=[]
 for x in p[:3]:
  y=x['y'];largest=max(x['labels'],key=lambda k:int((y==k).sum()));rr=[{'cluster_id':int(k),'label':x['labels'][k] if k>=0 else 'noise','cluster_size':int((y==k).sum()),'changed_inputs':int(((y==k)&changed).sum())} for k in sorted(set(y.tolist()))];impact.append({'partition':x['name'],'changed_assigned':int((changed&(y>=0)).sum()),'changed_noise':int((changed&(y==-1)).sum()),'largest_cluster':next(r for r in rr if r['cluster_id']==largest),'per_cluster':rr});assert sum(r['changed_inputs'] for r in rr)==6497
 (d/'wos_affected_old_partitions.private.json').write_text(json.dumps({'scope':'old frozen partitions only; not measured effect on new membership','affected_text_rows':int(changed.sum()),'partitions':impact},indent=2,ensure_ascii=False))
 repair=json.loads((d/'wos_text_restoration_report.private.json').read_text());assert repair['counts']['text_changed']==6497;assert sha(d/'corrected_full_inputs.private.jsonl.gz')==repair['outputs']['corrected_full_inputs.private.jsonl.gz']['sha256'];
 corrected_manifest={'schema':'pro-adherence-stage3-pubmedbert-full-input/v1','status':'CORRECTED_WOS_FIELDS_FULL_INPUT_PREPARED_NOT_INFERRED','frozen_stage2_sha256':repair['source_sha256']['frozen_stage2.zip'],'frozen_roster_sha256':repair['source_sha256']['STAGE3_20261110_PRIVATE_article_eligibility.jsonl.gz'],'number_eligible':57204,'number_writable':57204,'text_states':{'title_abstract':55675,'title_only':1529},'source_counts':{'pubmed':49870,'woscc':6606,'apa_psycinfo':728},'input_sha256':sha(d/'corrected_full_inputs.private.jsonl.gz'),'input_bytes':(d/'corrected_full_inputs.private.jsonl.gz').stat().st_size,'input_name':'full_pubmedbert_inputs.private.jsonl.gz','missing_article_ids':[],'text_selection':'approved single complete record PubMed > WoS > APA, title-only iff no abstract, WoS AB/PY restored directly from exact source; strips same as original','no_inference_executed':True,'publication_authorized':False,'text_changed':6497,'original_input_zip_sha256':repair['source_sha256']['STAGE3_20261112_PRIVATE_FULL_PUBMEDBERT_INPUTS.zip']}
 assert sum(corrected_manifest['source_counts'].values())==57204 and sum(corrected_manifest['text_states'].values())==57204
 (d/'corrected_full_inputs_manifest.private.json').write_text(json.dumps(corrected_manifest,indent=2))
 src_names=['stage3_temporal_years.py','stage3_temporal_fixed.py','stage3_temporal_refit.py','stage3_temporal_audit.py','stage3_restore_wos_text.py','stage3_temporal_finalize.py']
 src={n:root/n for n in src_names};assert all(p.is_file() for p in src.values())
 common={'publication_years.private.jsonl.gz':d/'publication_years.private.jsonl.gz','year_report.private.json':d/'year_report.private.json'}
 pack(root/'STAGE3_20261127_PRIVATE_WOS_TEXT_RESTORATION.zip',{'full_pubmedbert_inputs.private.jsonl.gz':d/'corrected_full_inputs.private.jsonl.gz','full_inputs_manifest.private.json':d/'corrected_full_inputs_manifest.private.json','corrected_input_changes.private.jsonl.gz':d/'corrected_input_changes.private.jsonl.gz','wos_text_restoration_report.private.json':d/'wos_text_restoration_report.private.json','wos_affected_old_partitions.private.json':d/'wos_affected_old_partitions.private.json',**common,**{n:src[n] for n in ['stage3_temporal_years.py','stage3_temporal_fixed.py','stage3_restore_wos_text.py','stage3_temporal_finalize.py']}},'Corrected input candidate, 6497 text changes, original frozen Stage2 untouched; no corrected embeddings or clusters computed')
 temporal={**common,**{p.name:p for p in d.glob('temporal_*.private.*')},**{p.name:p for p in d.glob('refit_*.private.*')},'wos_text_restoration_report.private.json':d/'wos_text_restoration_report.private.json','wos_affected_old_partitions.private.json':d/'wos_affected_old_partitions.private.json',**src};assert len(temporal)>=25
 pack(root/'STAGE3_20261127_PRIVATE_TEMPORAL_SAME_SIZE_DIAGNOSTICS.zip',temporal,'Fixed map 28 partitions and 33 early equal-size subsets, 363 output partitions; semantic results diagnostic of old incomplete text input; graph results within observed exact DOI coverage, no scientific validation or Stage gate')
 for n,p in src.items():
  q=root/f'STAGE3_20261127_SOURCE_{n}.txt';q.write_bytes(p.read_bytes());q.chmod(0o600);print(q.name,sha(q),flush=True)
if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))

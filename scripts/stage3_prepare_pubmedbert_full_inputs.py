"""Offline, restricted full-corpus input preparation from the approved stage 2 sources.
Exactly the P1 source text rule; no model weights or inference.
"""
import os,zipfile,gzip,json,hashlib,collections,re,time
from pathlib import Path
ROOT=Path('/mnt/data');OUT=Path('/tmp/pro_adherence_full_pubmedbert');OUT.mkdir(mode=0o700,parents=True,exist_ok=True)
archive=ROOT/'Stage2_frozen_PRIVATE.zip';roster=ROOT/'STAGE3_20261110_PRIVATE_article_eligibility.jsonl.gz';
expected=[('archive',archive,'a76f8cd2acae907c163c417e1ccc7900275f6c12a1e689d591c922b865d41127'),('eligibility',roster,'c080449e4a3450e6ff2e396c0463d05960d8b1cd101f42c7f99ccf3ab202e234')]
for label,p,sha in expected:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
 print('INPUT',label,'sha_ok',h.hexdigest()==sha,'bytes',p.stat().st_size,flush=True)
 if h.hexdigest()!=sha:raise ValueError(label+' hash differs')
source_ids={};info={}
with gzip.open(roster,'rt',encoding='utf8') as f:
 for line in f:
  row=json.loads(line)
  if not row['primary_eligible']:continue
  aid=row['article_id'];record_ids=row['source_record_ids']
  if aid in info:raise ValueError('duplicate canonical')
  info[aid]={'record_ids':set(record_ids),'peer_review_unknown':row['peer_review_unknown'],'wos_nr_cr_mismatch':row['wos_nr_cr_mismatch']}
  for sid in record_ids:
   if sid in source_ids:raise ValueError('source double membership')
   source_ids[sid]=aid
assert len(info)==57204,len(info)
rows=collections.defaultdict(list)
with zipfile.ZipFile(archive) as z:
 if z.testzip() is not None:raise ValueError('bad zip CRC')
 with gzip.GzipFile(fileobj=z.open('source_records.jsonl.gz'),mode='rb') as f:
  for b in f:
   r=json.loads(b)
   aid=source_ids.get(r['source_record_id'])
   if aid is not None:
    rows[aid].append({'source_id':r['source_id'],'source_record_id':r['source_record_id'],
                    'title':(r.get('title') or '').strip(),'abstract':(r.get('abstract') or '').strip(),
                    'year':r.get('year'),'raw_export_sha256':r.get('raw_export_sha256'),
                    'raw_record_ordinal':r.get('raw_record_ordinal')})
def select(records):
 precedence={'pubmed':0,'woscc':1,'apa_psycinfo':2}
 records=sorted(records,key=lambda r:(precedence[r['source_id']],r['source_record_id']))
 both=next((r for r in records if r['title'] and r['abstract']),None)
 if both:return both,'title_abstract'
 if any(r['abstract'] for r in records):return None,'requires_source_resolution'
 title=next((r for r in records if r['title']),None)
 if title:return title,'title_only'
 return None,'missing_input'
counts=collections.Counter();bySource=collections.Counter();allrows=[];bad=[]
for aid in sorted(info):
 rr=rows.get(aid,[])
 if {r['source_record_id'] for r in rr}!=info[aid]['record_ids']:
  raise ValueError('incomplete sources for '+aid)
 selected,state=select(rr);counts[state]+=1
 if state not in ('title_abstract','title_only'):
  bad.append(aid);continue
 bySource[selected['source_id']]+=1
 allrows.append({'article_id':aid,'source_record_id':selected['source_record_id'],'source_id':selected['source_id'],
                 'title':selected['title'],'abstract':selected['abstract'] if state=='title_abstract' else None,
                 'text_state':state,'year_raw':selected['year'],
                 'raw_export_sha256':selected['raw_export_sha256'],'raw_record_ordinal':selected['raw_record_ordinal'],
                 'peer_review_unknown':info[aid]['peer_review_unknown'],
                 'wos_nr_cr_mismatch':info[aid]['wos_nr_cr_mismatch']})
with zipfile.ZipFile(ROOT/'STAGE3_P1_20261111_PRIVATE_INPUTS.zip') as z:
 with gzip.GzipFile(fileobj=z.open('pilot_1000_inputs.private.jsonl.gz'),mode='rb') as f:
  pilot=[json.loads(l) for l in f if l.strip()]
allmap={r['article_id']:r for r in allrows}
for a in pilot:
 b=allmap.get(a['article_id'])
 assert b is not None,a['article_id']
 for field in ('source_record_id','source_id','title','abstract','text_state','raw_export_sha256'):
  if a.get(field)!=b.get(field):raise ValueError('P1 source mismatch '+field)
print('STATE',dict(counts),'SOURCES',dict(bySource),'P1_CONSISTENCY',len(pilot),'ERRORS',len(bad),flush=True)
name='full_pubmedbert_inputs.private.jsonl.gz';path=OUT/name
with path.open('wb') as f:
 with gzip.GzipFile(fileobj=f,mode='wb',filename='',mtime=0,compresslevel=6) as g:
  for r in allrows:g.write((json.dumps(r,ensure_ascii=False,separators=(',',':'),sort_keys=True)+'\n').encode('utf8'))
h=hashlib.sha256(path.read_bytes()).hexdigest()
manifest={'schema':'pro-adherence-stage3-pubmedbert-full-input/v1',
          'status':'FULL_INPUT_PREPARED_NOT_FULL_INFERRED','frozen_stage2_sha256':expected[0][-1],
          'frozen_roster_sha256':expected[1][-1],'number_eligible':57204,'number_writable':len(allrows),
          'text_states':dict(counts),'source_counts':dict(bySource),
          'p1_source_match_count':len(pilot),'input_sha256':h,'input_bytes':path.stat().st_size,
          'input_name':name,'missing_article_ids':bad,
          'text_selection':'single-complete-source PubMed>WoS>APA, title-only iff no source contains an abstract',
          'no_inference_executed':True,'publication_authorized':False}
m=OUT/'full_inputs_manifest.private.json';m.write_text(json.dumps(manifest,sort_keys=True,indent=2,ensure_ascii=False)+'\n')
print('DONE',path,path.stat().st_size,h,'manifest',hashlib.sha256(m.read_bytes()).hexdigest(),flush=True)

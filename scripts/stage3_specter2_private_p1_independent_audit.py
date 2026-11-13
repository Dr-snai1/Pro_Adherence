"""Independent READ-ONLY private 1000x768 SPECTER2 P1 archive auditor.

No model import/inference and no publication of private identifiers/text/vectors.
"""
from __future__ import annotations
import argparse,gzip,hashlib,io,json,zipfile
from collections import Counter
from pathlib import Path
import numpy as np
SRC_SHA='b37128da2ef9fc6f15834c48a537b4ddb9ae7475dafcf7e0bb7fec586737d23b'
N,D=1000,768

def digest(b):return hashlib.sha256(b).hexdigest()
def sha_file(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def audit(outzip,sample,output):
 if output.exists():raise RuntimeError('refuse overwrite independent audit')
 if sha_file(sample)!=SRC_SHA:raise RuntimeError('private source sample SHA mismatch')
 with gzip.open(sample,'rt') as f:original=[json.loads(l) for l in f]
 if len(original)!=N or len({r['article_id'] for r in original})!=N:
  raise RuntimeError('independent source sample roster mismatch')
 with zipfile.ZipFile(outzip) as z:
  if z.testzip() is not None:raise RuntimeError('archive CRC mismatch')
  m=json.loads(z.read('manifest.private.json'))
  r=json.loads(z.read('report.private.json'))
  if m['pilot_sample_sha256']!=SRC_SHA:raise RuntimeError('wrong pilot source')
  for name,meta in m['files'].items():
   b=z.read(name)
   if len(b)!=meta['bytes'] or digest(b)!=meta['sha256']:
    raise RuntimeError('archive file digest mismatch: '+name)
  raw=np.load(io.BytesIO(z.read('raw.float32.npy')),allow_pickle=False)
  norm=np.load(io.BytesIO(z.read('raw_l2_norm.float64.npy')),allow_pickle=False)
  unit=np.load(io.BytesIO(z.read('unit.float32.npy')),allow_pickle=False)
  if raw.shape!=(N,D) or unit.shape!=(N,D) or norm.shape!=(N,):raise RuntimeError('wrong output dimensions')
  if raw.dtype!=np.float32 or unit.dtype!=np.float32 or norm.dtype!=np.float64:
   raise RuntimeError('wrong output dtype')
  if not np.isfinite(raw).all() or not np.isfinite(norm).all() or not np.isfinite(unit).all():
   raise RuntimeError('nonfinite output')
  if np.any(norm<=0) or not np.allclose(np.linalg.norm(raw.astype('float64'),axis=1),norm,atol=1e-6,rtol=1e-5):
   raise RuntimeError('raw vector norm mismatch')
  if not np.allclose(np.linalg.norm(unit.astype('float64'),axis=1),1,atol=1e-5,rtol=0):
   raise RuntimeError('unit vector not normalized')
  if not np.allclose(unit.astype('float64')*norm[:,None],raw.astype('float64'),atol=3e-6,rtol=3e-6):
   raise RuntimeError('raw vector reconstruction mismatch')
  with gzip.GzipFile(fileobj=io.BytesIO(z.read('pilot_1000_status.private.jsonl.gz')),mode='rb') as f:
   roster=[json.loads(line) for line in f]
  if len(roster)!=N:raise RuntimeError('status roster count mismatch')
  all_src=[]
  for i,(src,record) in enumerate(zip(original,roster)):
   text=src['title']+'[SEP]'+(src.get('abstract') or '')
   expected_text_sha=digest(text.encode('utf-8'))
   if (record['canonical_article_id']!=src['article_id'] or record['vector_row']!=i
       or record['status']!='ready' or record['source_id']!=src['source_id']
       or record['source_record_id']!=src['source_record_id']
       or record['text_sha256']!=expected_text_sha
       or record['title_only']!=(src['text_state']=='title_only')
       or record['tokens_lost']!=record['untruncated_tokens']-record['encoded_tokens']
       or record['encoded_tokens']>512 or record['encoded_tokens']<=0
       or record['tokens_lost']<0):
    raise RuntimeError('independent row identity or token/accounting mismatch')
   all_src.append(record['source_id'])
  if dict(Counter(all_src))!={'pubmed':873,'woscc':90,'apa_psycinfo':37}:
   raise RuntimeError('source stratification mismatch')
  num_smoke=sum(bool(x['p1_64_numeric_gate']) for x in roster)
  trunc=sum(x['tokens_lost']>0 for x in roster)
  lost=sum(x['tokens_lost'] for x in roster)
  title_only=sum(x['title_only'] for x in roster)
  if num_smoke!=64 or trunc!=r['counts']['truncated_count'] or lost!=r['counts']['lost_tokens_total'] or title_only!=r['counts']['title_only_count']:
   raise RuntimeError('independent aggregate audit mismatch')
  if r['complete_private_corpus_inference_executed'] or r['full_57204_production_vectors_created'] or m['stage_gate_authorized']:
   raise RuntimeError('misrepresented scope/status')
 report={'schema':'pro-adherence-stage3-specter2-p1-independent-audit/v1',
         'status':'INDEPENDENT_PRIVATE_64_AND_1000_AUDIT_PASS',
         'input_sample_sha256':SRC_SHA,'output_zip_sha256':sha_file(outzip),
         'source_rows':N,'vector_dimensions':[N,D],'smoke_rows':num_smoke,
         'ready_rows':N,'title_only_rows':title_only,'truncated_rows':trunc,
         'total_tokens_lost':lost,'all_finite_norms_reconstruction':True,
         'exact_article_order_and_text_shas':True,'source_counts':dict(Counter(all_src)),
         'full_57204_inference_done':False,'private_outputs_published':False,
         'stage3_closed':False}
 output.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'asset_sha':report['output_zip_sha256'],'trunc':trunc},sort_keys=True))
 return report
if __name__=='__main__':
 p=argparse.ArgumentParser()
 p.add_argument('--output-zip',required=True,type=Path)
 p.add_argument('--sample',required=True,type=Path)
 p.add_argument('--out',required=True,type=Path)
 a=p.parse_args();audit(a.output_zip,a.sample,a.out)

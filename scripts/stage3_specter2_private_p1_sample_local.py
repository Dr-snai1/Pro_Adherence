"""Private-only Stage3 P1 exact historical sample reconstruction; no model inference."""
from pathlib import Path
import zipfile,gzip,hashlib,json,re
from collections import Counter,defaultdict
from datetime import date
BASE=Path('/mnt/data')
GRAPH=BASE/'STAGE3_20261111_PRIVATE_node2vec_graph.zip'
INPUT=BASE/'STAGE3_20261112_PRIVATE_FULL_PUBMEDBERT_INPUTS.zip'
EXPECTED={'GRAPH':'33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c','FILE':'1611f07e18ccf999493938e552d1a73ad049db931a11399fc01f0ca7b07dc053'}
SEED='stage3-p1-fixed-20261031'
def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def sample():
 assert sha(GRAPH)==EXPECTED['GRAPH']
 deg=Counter()
 with zipfile.ZipFile(GRAPH) as z:
  assert z.testzip() is None
  with gzip.open(z.open('node2vec_training_edges.private.jsonl.gz'),'rt') as f:
   n=0
   for line in f:
    e=json.loads(line);deg[e['source_article_id']]+=1;deg[e['target_article_id']]+=1;n+=1
   assert n==328298
 with zipfile.ZipFile(INPUT) as z:
  assert z.testzip() is None
  fn='full_pubmedbert_inputs.private.jsonl.gz'
  assert hashlib.sha256(z.read(fn)).hexdigest()==EXPECTED['FILE']
  with gzip.open(z.open(fn),'rt') as f: rows=[json.loads(line) for line in f]
 assert len(rows)==57204 and len({r['article_id'] for r in rows})==57204
 def yb(v):
  m=re.search(r'(?<!\d)(18\d\d|19\d\d|20\d\d)(?!\d)',v or '')
  return 'year_unknown' if not m else ('year_pre2000' if int(m.group(1))<2000 else 'year_2000s' if int(m.group(1))<2010 else 'year_2010s' if int(m.group(1))<2020 else 'year_2020plus')
 def db(n):return 'degree_zero' if n==0 else 'degree_1_4' if n<=4 else 'degree_5_19' if n<20 else 'degree_20plus'
 def rank(a):return hashlib.sha256((SEED+':'+a).encode()).hexdigest()
 def strata(r):
  labels=[r['text_state'],yb(r['year_raw']),db(deg[r['article_id']]),'source_'+r['source_id']]
  if r['peer_review_unknown']:labels.append('flag_peer_review_unknown')
  if r['wos_nr_cr_mismatch']:labels.append('flag_wos_nr_cr_mismatch')
  if r['abstract'] and len(r['abstract'])>=2500:labels.append('long_abstract_candidate')
  return labels
 buckets=defaultdict(list)
 for row in rows:
  for label in strata(row):buckets[label].append(row)
 chosen={}
 for label in sorted(buckets):
  for row in sorted(buckets[label],key=lambda r:(rank(r['article_id']),r['article_id']))[:20]:
   if len(chosen)>=1000:break
   chosen[row['article_id']]=row
 for row in sorted(rows,key=lambda r:(rank(r['article_id']),r['article_id'])):
  if len(chosen)>=1000:break
  chosen[row['article_id']]=row
 result=[chosen[k] for k in sorted(chosen)]
 print('SOURCE',dict(Counter(r['source_id'] for r in result)))
 print('ISOLATES',sum(deg[r['article_id']]==0 for r in result))
 print('STATE',dict(Counter(r['text_state'] for r in result)))
 print('FLAG',sum(r['peer_review_unknown'] for r in result),sum(r['wos_nr_cr_mismatch'] for r in result))
 print('YEAR',dict(Counter(yb(r['year_raw']) for r in result)))
 print('DEG',dict(Counter(db(deg[r['article_id']]) for r in result)))
 out=BASE/'STAGE3_20261113_PRIVATE_SPECTER2_APPROVED_P1_1000_INPUTS.jsonl.gz'
 assert not out.exists()
 with out.open('xb') as dest:
  with gzip.GzipFile(filename='',fileobj=dest,mode='wb',mtime=0,compresslevel=6) as z:
   for r in result:
    z.write((json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode())
 from hashlib import sha256
 print('SELECTED',len(result),'BYTES',out.stat().st_size,'SHA256',sha(out))
 return result,deg
if __name__=='__main__':sample()

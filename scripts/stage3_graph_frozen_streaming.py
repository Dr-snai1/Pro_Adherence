"""Stage 3 accepted frozen research layout → restricted citation graph.

This EXACT streaming script was used to materialize and independently replay
the 2026-11-11 private graph. It reads Stage2's actual research fields
(resolution, target_canonical_article_id, reference_ordinal); they differ from
the separate GitHub one-shot adapter schema. No scientific policy change.
No model downloads, training, or publication.
"""
import argparse, collections, gzip, hashlib, json, os, sqlite3, zipfile, time, tempfile
# This frozen-research loader uses assertions as scientific input invariants.
# Python -O removes them, so refuse optimized execution before any data read.
if not __debug__:
 raise RuntimeError('Stage3 graph input validation requires Python assertions (-O forbidden)')
from pathlib import Path
parser=argparse.ArgumentParser(description='Stage3 restricted frozen-research citation graph, no training')
parser.add_argument('--archive',required=True,type=Path)
parser.add_argument('--private-cohort',required=True,type=Path)
parser.add_argument('--private-output-dir',required=True,type=Path)
parser.add_argument('--prepare-private-graph',action='store_true')
args=parser.parse_args()
if not args.prepare_private_graph: parser.error('explicit --prepare-private-graph flag required')
P,C,O=args.archive,args.private_cohort,args.private_output_dir
if O.exists() and any(O.iterdir()): parser.error('destination is not empty; cannot overwrite')
ARCH='a76f8cd2acae907c163c417e1ccc7900275f6c12a1e689d591c922b865d41127'
COHORT='c080449e4a3450e6ff2e396c0463d05960d8b1cd101f42c7f99ccf3ab202e234'
def sh(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def readz(z,name):
 with z.open(name) as f, gzip.GzipFile(fileobj=f) as gz:
  for line in gz:
   if line.strip(): yield json.loads(line)
def readgz(path):
 with gzip.open(path,'rb') as f:
  for line in f:
   if line.strip(): yield json.loads(line)
assert sh(P)==ARCH and sh(C)==COHORT
roster={}; status=collections.Counter()
for r in readgz(C):
 k=r['article_id']; assert k not in roster and type(r['primary_eligible']) is bool
 roster[k]=r['primary_eligible']; status[r['eligibility_status']]+=1
assert len(roster)==57293 and sum(roster.values())==57204
print('roster: verified',len(roster),sum(roster.values()),status,flush=True)
O.mkdir(mode=0o700,exist_ok=True); os.chmod(O,0o700)
work=tempfile.TemporaryDirectory(prefix='stage3_graph_sqlite_')
db=sqlite3.connect(str(Path(work.name)/'scratch_graph.sqlite'))
db.execute('PRAGMA journal_mode=OFF');db.execute('PRAGMA synchronous=OFF');db.execute('PRAGMA temp_store=FILE')
db.execute('CREATE TABLE citation (src TEXT, dst TEXT, source_id TEXT, ordinal INTEGER, export_sha TEXT, record_ordinal INTEGER, eligible_pair INTEGER, self_loop INTEGER)')
db.execute('CREATE TABLE source (id TEXT PRIMARY KEY, article_id TEXT, raw_export_sha TEXT, record_ordinal INTEGER, references_length INTEGER, ref_coverage TEXT)')
sids={}; article_src={}; s_counts=collections.Counter(); start=time.monotonic()
with zipfile.ZipFile(P) as z:
 assert z.testzip() is None
 manifest=json.load(z.open('manifest.json'))
 assert manifest['canonical_articles']==57293 and manifest['source_records']==87511 and manifest['publication_authorized'] is False
 article_ids=set()
 for r in readz(z,'canonical_articles.jsonl.gz'):
  a=r['canonical_article_id']; assert a not in article_ids;article_ids.add(a)
  for sid in r['source_record_ids']:
   assert sid not in sids;sids[sid]=a
 assert set(roster)==article_ids
 source_map={}
 for r in readz(z,'source_records.jsonl.gz'):
  sid=r['source_record_id'];assert sid in sids and sid not in source_map
  refs=r.get('cited_references_raw'); rawsha=r.get('raw_export_sha256')
  source_map[sid]=(rawsha,r.get('raw_record_ordinal'),len(refs) if isinstance(refs,list) else -1,r.get('reference_coverage','unknown'))
  s_counts[r.get('source_id')]+=1
 assert len(source_map)==87511 and set(source_map)==set(sids)
 print('source: verified',len(source_map),s_counts,'elapsed',round(time.monotonic()-start,1),flush=True)
 counts=collections.Counter();seen=set(); batches=[]; rows=0
 for r in readz(z,'citation_links.jsonl.gz'):
  method=r['resolution']; counts[method]+=1
  sid=r['citing_source_record_id']; sha,record_ordinal,ref_length,coverage=source_map[sid]
  o=r['reference_ordinal']
  assert isinstance(o,int) and o>=1 and not isinstance(o,bool)
  assert r['raw_export_sha256']==sha and r['citing_canonical_article_id']==sids[sid]
  assert len(sha)==64 and o<=ref_length and coverage!='not_exposed'
  # No observed reference can be repeated in source, including unresolved.
  key=(sid,o);assert key not in seen;seen.add(key)
  dst=r.get('target_canonical_article_id')
  if method=='exact_doi':
   assert dst in article_ids
   a=sids[sid]; ok=int(roster[a] and roster[dst]);loop=int(a==dst)
   batches.append((a,dst,sid,o,sha,record_ordinal,ok,loop))
   if len(batches)>=5000:
    db.executemany('INSERT INTO citation VALUES (?,?,?,?,?,?,?,?)',batches); batches.clear()
  else: assert dst is None and method in ('ambiguous_doi','unresolved')
  rows+=1
 if batches: db.executemany('INSERT INTO citation VALUES (?,?,?,?,?,?,?,?)',batches)
 db.commit()
 assert rows==2437863 and counts=={'exact_doi':406811,'ambiguous_doi':223,'unresolved':2030829},(rows,counts)
 print('citation: verified', rows,counts,'elapsed',round(time.monotonic()-start,1),flush=True)
 db.execute('CREATE INDEX idx_src_dst ON citation(src,dst)')
 db.execute('CREATE INDEX idx_elig ON citation(eligible_pair,self_loop)')
 db.commit()

def gzout(name,iterator):
 p=O/name
 assert not p.exists()
 with p.open('xb') as target, gzip.GzipFile(filename='', fileobj=target,mode='wb',mtime=0,compresslevel=6) as out:
  n=0
  for row in iterator:
   out.write((json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode());n+=1
 return {'file_name':name,'row_count':n,'sha256':sh(p),'size_bytes':p.stat().st_size}

# Directed original edge graph includes excluded and self-citations.
def dir_edges():
 for a,b,count in db.execute('SELECT src,dst,COUNT(*) FROM citation GROUP BY src,dst ORDER BY src,dst'):
  yield {'source_article_id':a,'target_article_id':b,'observation_count':count,'weight':1}

def train_edges():
 # Binary, unique undirected graph. Reversed observations are grouped together.
 for a,b,n in db.execute('SELECT CASE WHEN src<dst THEN src ELSE dst END, CASE WHEN src<dst THEN dst ELSE src END, COUNT(*) FROM citation WHERE eligible_pair=1 AND self_loop=0 GROUP BY 1,2 ORDER BY 1,2'):
  assert a<b and roster[a] and roster[b]
  yield {'source_article_id':a,'target_article_id':b,'weight':1,'observation_count':n}

def mapping_rows():
 for n,a in enumerate(sorted(a for a,v in roster.items() if v)):
  yield {'node_index':n,'article_id':a}

# Evidence table separately retains every original verified source ordinal + SHA.
def citation_evidence():
 for a,b,sid,o,sha,record_ord,ok,loop in db.execute('SELECT src,dst,source_id,ordinal,export_sha,record_ordinal,eligible_pair,self_loop FROM citation ORDER BY src,dst,source_id,ordinal'):
  yield {'source_article_id':a,'target_article_id':b,'source_record_id':sid,'raw_reference_ordinal':o,'export_sha256':sha,'record_ordinal':record_ord}
outputs={}
for name,rows in [('directed_edges.private.jsonl.gz',dir_edges()),('node2vec_training_edges.private.jsonl.gz',train_edges()),('node2vec_node_mapping.private.jsonl.gz',mapping_rows()),('directed_citation_evidence.private.jsonl.gz',citation_evidence())]:
 outputs[name]=gzout(name,rows)
 print('output',name,outputs[name]['row_count'],outputs[name]['size_bytes'], 'elapsed',round(time.monotonic()-start,1),flush=True)
edge_obs=db.execute('SELECT COUNT(*) FROM citation').fetchone()[0]
train_obs=db.execute('SELECT COUNT(*) FROM citation WHERE eligible_pair=1 AND self_loop=0').fetchone()[0]
excluded=db.execute('SELECT SUM(eligible_pair=0),SUM(eligible_pair=1 AND self_loop=1) FROM citation').fetchone()
assert edge_obs==406811 and train_obs+sum(excluded)==edge_obs
neighbors={}
for a,b in db.execute('SELECT src,dst FROM citation WHERE eligible_pair=1 AND self_loop=0'):
 neighbors[a]=1;neighbors[b]=1
isolates=sum(a not in neighbors for a,v in roster.items() if v)
print('observations',edge_obs,train_obs,'exclusions',excluded,'isolates',isolates,flush=True)
manifest={'schema':'pro-adherence-stage3-private-node2vec-graph/v1','access_class':'restricted','publication_authorized':False,'frozen_stage2_zip_sha256':ARCH,'private_eligibility_sha256':COHORT,'source_records':87511,'canonical_groups':57293,'eligible_count':57204,'citations_status_counts':dict(counts),'directed_edge_count':outputs['directed_edges.private.jsonl.gz']['row_count'],'directed_observations':edge_obs,'node2vec_training_edge_count':outputs['node2vec_training_edges.private.jsonl.gz']['row_count'],'node2vec_training_observations':train_obs,'excluded_observations_by_policy':excluded[0],'excluded_observations_selfloop':excluded[1],'node2vec_training_isolates':isolates,'source_graph':'directed_with_self_and_excluded','node2vec_projection':'undirected_binary_unique_no_self_eligible_endpoints','outputs':outputs,'graph_snapshot':{'source_directed_graph_sha256':outputs['directed_edges.private.jsonl.gz']['sha256'],'training_undirected_graph_sha256':outputs['node2vec_training_edges.private.jsonl.gz']['sha256'],'sorted_node_mapping_sha256':outputs['node2vec_node_mapping.private.jsonl.gz']['sha256'],'eligible_node_count':57204,'training_orientation':'undirected','source_orientation':'directed','weights':'binary_unit'},'model_training_executed':False,'potential_walk_steps':57204*10*40,'raw_plus_unit_float32_min_bytes':57204*128*4*2}
(O/'node2vec_graph_manifest.private.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
print('manifest',sh(O/'node2vec_graph_manifest.private.json'),'elapsed',round(time.monotonic()-start,1),flush=True)
db.close()
work.cleanup()

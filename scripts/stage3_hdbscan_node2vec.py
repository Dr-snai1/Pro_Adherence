#!/usr/bin/env python3
"""Private exploratory HDBSCAN on frozen 43,608 node2vec unit 128d vectors. No PCA."""
import argparse,gzip,hashlib,io,json,os,platform,time,zipfile
from collections import Counter
from pathlib import Path
import numpy as np,sklearn
from sklearn.cluster import HDBSCAN
from sklearn.metrics import adjusted_rand_score
FROZEN_SHA='51f086fb71484065f54e4a8999528417607a817019feb13eef5941f9820947b4'
def sha(path):
 with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def execute(src,dst):
 assert sha(src)==FROZEN_SHA
 with zipfile.ZipFile(src) as z:
  assert z.testzip() is None
  meta=json.loads(z.read('manifest.private.json'))
  for name,detail in meta['files'].items():assert hashlib.sha256(z.read(name)).hexdigest()==detail['sha256'],name
  ids=np.load(io.BytesIO(z.read('node_indices.int32.npy')))
  unit=np.load(io.BytesIO(z.read('unit.float32.npy')))
  assert ids.shape==(43608,) and unit.shape==(43608,128) and np.all(np.diff(ids)>0)
  assert np.isfinite(unit).all() and max(abs(np.linalg.norm(unit,axis=1)-1))<3e-5
  roster=[]
  with gzip.open(z.open('article_status.private.jsonl.gz'),'rt') as stream:
   for i,line in enumerate(stream):
    r=json.loads(line);assert r['node_index']==i
    roster.append(r)
    if r['status']=='ready':assert ids[r['vector_row']]==i
    else:assert r['status']=='missing_structural' and r['vector_row'] is None
  assert len(roster)==57204 and Counter(r['status'] for r in roster)=={'ready':43608,'missing_structural':13596}
 assert not dst.exists();dst.mkdir(mode=0o700)
 settings=[30,80,150];labels=[];probs=[];runs=[];tstart=time.monotonic()
 for size in settings:
  t0=time.monotonic();model=HDBSCAN(min_cluster_size=size,min_samples=10,metric='euclidean',algorithm='auto',leaf_size=40,n_jobs=4,copy=True)
  lab=model.fit_predict(unit);p=model.probabilities_
  groups=Counter(map(int,lab[lab>=0]));assert set(groups)==set(range(len(groups)))
  assert np.isfinite(p).all() and np.all((p>=0)&(p<=1))
  report={'min_cluster_size':size,'min_samples':10,'clusters':len(groups),'noise':int(sum(lab<0)),
          'assigned':int(sum(lab>=0)),'largest_clusters':sorted(groups.values(),reverse=True)[:25],
          'run_seconds':round(time.monotonic()-t0,2)}
  print(json.dumps({'progress':'completed','run':report}),flush=True);runs.append(report);labels.append(lab.copy());probs.append(p.copy())
 sens=[]
 for i in range(len(settings)):
  for j in range(i+1,len(settings)):
   both=(labels[i]>=0)&(labels[j]>=0)
   sens.append({'min_cluster_size_A':settings[i],'min_cluster_size_B':settings[j],
    'ari_including_noise_as_label':float(adjusted_rand_score(labels[i],labels[j])),
    'both_assigned_rows':int(both.sum()),'ari_jointly_assigned':float(adjusted_rand_score(labels[i][both],labels[j][both])) if both.sum()>1 else None})
 idx={int(u):k for k,u in enumerate(ids)}
 path=dst/'node2vec_hdbscan_assignments.private.jsonl.gz'
 with open(path,'xb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0,compresslevel=6) as out:
  for k,r in enumerate(roster):
   i=idx.get(k)
   row={'article_id':r['canonical_article_id'],'node_index':k,'vector_status':r['status'],
        'results':None if i is None else [
           {'min_cluster_size':settings[j],'cluster':int(labels[j][i]) if labels[j][i]>=0 else None,
            'is_noise':bool(labels[j][i]<0),'membership_strength':float(probs[j][i])} for j in range(len(settings))]}
   out.write((json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode('utf8'))
 with gzip.open(path,'rt') as inp:
  counter=Counter(); n=0
  for line in inp:
   r=json.loads(line);counter[r['vector_status']]+=1;n+=1
 assert n==57204 and counter=={'ready':43608,'missing_structural':13596}
 summary={'schema':'pro-adherence-stage3-hdbscan-node2vec-exploratory/v1','frozen_source_sha256':FROZEN_SHA,
 'frozen_source_drive_id':'1EZni6ZnorzRiENZcVH6jASAxnXiNPYGR','vectors':43608,'missing_structural':13596,
 'unit_dimensions':128,'input_transform':'none','algorithm':'sklearn.cluster.HDBSCAN',
 'metric':'euclidean_on_L2_unit (distance monotonic with cosine; not equal for density algorithm)',
 'min_samples':10,'runs':runs,'sensitivity':sens,'total_seconds':round(time.monotonic()-tstart,2),
 'scientific_acceptance':False,'caveats':['noise is distinct from missing_structural','no semantic topic claims','min_cluster_size choices exploratory, not accepted defaults','min_samples fixed; no other embedding lenses tested']}
 summary_path=dst/'node2vec_hdbscan_summary.private.json';summary_path.write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
 manifest={'schema':'pro-adherence-stage3-private-hdbscan-execution/v1','status':'LOCAL_VALIDATED_PENDING_REMOTE_READBACK',
 'source_zip_sha256':FROZEN_SHA,'runner_sha256':sha(__file__),'python':platform.python_version(),'sklearn':sklearn.__version__,
 'outputs':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in [path,summary_path]}}
 (dst/'node2vec_hdbscan_manifest.private.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'final':'COMPLETE','summary':summary,'manifest':manifest}),flush=True)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--src',type=Path,required=True);a.add_argument('--dst',type=Path,required=True);args=a.parse_args();execute(args.src,args.dst)

#!/usr/bin/env python3
"""Exact full-cohort HDBSCAN: one frozen 768d unit vector per article per semantic view.

Uses sklearn 1.8.0 HDBSCAN full fit, no PCA / approximations, and exact
single-linkage tree to extract EOM solutions at fixed mcs 30, 80, 150.
Raw research observations remain in restricted Drive only.
"""
import argparse,hashlib,json,gzip,os,platform,time,collections,resource
from pathlib import Path
import numpy as np,sklearn
from sklearn.cluster import HDBSCAN
from sklearn.cluster._hdbscan.hdbscan import tree_to_labels

def sha(path):
 with open(path,'rb') as h:return hashlib.file_digest(h,'sha256').hexdigest()

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--matrix',required=True,type=Path);ap.add_argument('--roster',required=True,type=Path)
 ap.add_argument('--view',choices=['pubmedbert_cls','pubmedbert_mean','specter2_proximity'],required=True)
 ap.add_argument('--out',required=True,type=Path);ap.add_argument('--min-samples',type=int,default=10)
 ap.add_argument('--n-jobs',type=int,default=4);a=ap.parse_args()
 a.out.mkdir(parents=True,exist_ok=True);os.chmod(a.out,0o700)
 if (a.out/'summary.private.json').exists():raise FileExistsError('Existing result not overwritten')
 print(json.dumps({'stage':'load','view':a.view,'matrix':str(a.matrix)}),flush=True)
 X=np.load(a.matrix,mmap_mode='r'); assert X.shape==(57204,768) and X.dtype==np.float32
 # sklearn converts internally to float64; memmap preserves input original bytes unchanged.
 ids=[json.loads(line)['article_id'] for line in gzip.open(a.roster,'rt')]
 assert len(ids)==57204 and len(set(ids))==57204
 start=time.time()
 model=HDBSCAN(min_cluster_size=30,min_samples=a.min_samples,metric='euclidean',algorithm='auto',n_jobs=a.n_jobs,
               leaf_size=40,cluster_selection_method='eom',allow_single_cluster=False,copy=True)
 print(json.dumps({'stage':'hdbscan_fit_start','view':a.view,'n':len(X),'dim':768,'min_samples':a.min_samples,'time':time.strftime('%FT%T',time.gmtime())}),flush=True)
 labels0=model.fit_predict(X)
 elapsed=time.time()-start
 print(json.dumps({'stage':'hdbscan_fit_completed','view':a.view,'elapsed_s':round(elapsed,2),'maxrss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)}),flush=True)
 results={};labels={};probs={}
 for threshold in (30,80,150):
  la,pr=tree_to_labels(model._single_linkage_tree_,threshold,cluster_selection_method='eom',allow_single_cluster=False,
                       cluster_selection_epsilon=0.0,max_cluster_size=None)
  la=np.asarray(la,dtype=np.int32);pr=np.asarray(pr,dtype=np.float64)
  assert len(la)==57204 and np.isfinite(pr).all() and np.all((pr>=0)&(pr<=1))
  assert threshold!=30 or np.array_equal(la,labels0)
  unique,ct=np.unique(la[la>=0],return_counts=True)
  assert np.array_equal(unique,np.arange(len(unique)))
  labels[threshold]=la;probs[threshold]=pr
  results[str(threshold)]={'cluster_count':len(unique),'assigned':int((la>=0).sum()),'noise':int((la<0).sum()),
    'sizes_descending':sorted((int(c) for c in ct),reverse=True), 'max_probability':float(pr.max()),'min_probability':float(pr.min())}
  print(json.dumps({'stage':'threshold','view':a.view,'mcs':threshold,'clusters':len(unique),'noise':results[str(threshold)]['noise']}),flush=True)
 out=a.out/'assignments.private.jsonl.gz'
 with open(out,'xb') as f, gzip.GzipFile(fileobj=f,mode='wb',filename='',mtime=0,compresslevel=5) as g:
  for i,aid in enumerate(ids):
   record={'article_id':aid,'node_index':i,'labels':{str(k):int(la[i]) if la[i]>=0 else None for k,la in labels.items()},
           'noise':{str(k):bool(la[i]<0) for k,la in labels.items()},
           'membership_strength':{str(k):float(pr[i]) for k,pr in probs.items()}}
   g.write((json.dumps(record,sort_keys=True,separators=(',',':'))+'\n').encode())
 summary={'schema':'pro-adherence-stage3-full-semantic-hdbscan/v1','view':a.view,'status':'FULL_57204_EXACT_HDBSCAN_LOCAL_COMPUTED',
    'count':57204,'dimension':768,'method':'sklearn HDBSCAN euclidean on original 768d unit vectors; EOM, no PCA/UMAP',
    'min_samples':a.min_samples,'min_cluster_size':[30,80,150],'fit_runtime_seconds':elapsed,
    'matrix_sha256':sha(a.matrix),'roster_sha256':sha(a.roster),
    'sklearn':sklearn.__version__,'numpy':np.__version__,'python':platform.python_version(),
    'results':results,'note':'Data-derived clusters only, no claims of scientific thematic validity'}
 (a.out/'summary.private.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
 manifest={'schema':'pro-adherence-stage3-full-semantic-hdbscan-execution/v1','view':a.view,
   'data_paths':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in [a.out/'summary.private.json',out]},
   'runner_sha256':sha(__file__),'input_matrix_sha256':sha(a.matrix),'input_roster_sha256':sha(a.roster)}
 (a.out/'manifest.private.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'stage':'done','view':a.view,'manifest':manifest}),flush=True)
if __name__=='__main__':main()

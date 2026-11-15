#!/usr/bin/env python3
"""Exact HDBSCAN via BLAS pairwise Euclidean and disk-backed Prim MST.

Intended for bounded-RAM CPUs: full n*n distance matrix stored on local disk,
never subsampled. Checks bitwise source SHA and uses sklearn's SAME exact
MST-to-EOM cluster-label implementation. No reduction or approximate kNN.
"""
import os,sys,hashlib,json,gzip,math,time,argparse,platform,resource
from pathlib import Path
import numpy as np
from sklearn.cluster._hdbscan._linkage import MST_edge_dtype
from sklearn.cluster._hdbscan.hdbscan import _process_mst,tree_to_labels
from sklearn.metrics import adjusted_rand_score
import sklearn

def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def compute_single_linkage(X, scratch, min_samples=10, block=256, debug=False):
 n,d=X.shape
 assert X.dtype==np.float64 and np.isfinite(X).all()
 path=Path(scratch); size=n*n*8
 free=os.statvfs(str(path.parent));freebytes=free.f_bavail*free.f_frsize
 if freebytes<size+400_000_000:raise OSError(f'not enough disk for {size} bytes + workspace; free {freebytes}')
 # Save exact float64 distances to disk; do not use float32 approximations.
 D=np.memmap(path,mode='w+',dtype=np.float64,shape=(n,n))
 norms=np.einsum('ij,ij->i',X,X,dtype=np.float64)
 core=np.empty(n,dtype=np.float64)
 t0=time.time()
 for start in range(0,n,block):
  end=min(n,start+block)
  B=X[start:end]@X.T
  B*=-2
  B+=norms[start:end,None]
  B+=norms[None,:]
  np.maximum(B,0.0,out=B);np.sqrt(B,out=B)
  for k in range(start,end):B[k-start,k]=0.0
  core[start:end]=np.partition(B,min_samples-1,axis=1)[:,min_samples-1]
  D[start:end,:]=B
  if debug and (start//block)%max(1,2048//block)==0:print(json.dumps({'stage':'dense_distance','rows':end,'of':n,'elapsed_s':round(time.time()-t0)}),flush=True)
 D.flush()
 if debug:print(json.dumps({'stage':'distance_complete','elapsed_s':round(time.time()-t0,2),'core_min':float(core.min()),'core_max':float(core.max())}),flush=True)
 mst=np.empty(n-1,dtype=MST_edge_dtype)
 visited=np.zeros(n,dtype=bool);visited[0]=True
 parent=np.zeros(n,dtype=np.int64)
 key=np.maximum(np.maximum(core[0],core),D[0,:]);key[0]=np.inf
 t1=time.time()
 for m in range(n-1):
  j=int(np.argmin(key));w=float(key[j]);assert np.isfinite(w)
  mst[m]['current_node']=int(parent[j]);mst[m]['next_node']=j;mst[m]['distance']=w
  visited[j]=True;key[j]=np.inf
  cand=np.maximum(np.maximum(core[j],core),D[j,:])
  update=(cand<key)&(~visited)
  parent[update]=j;key[update]=cand[update]
  if debug and m>0 and m%5000==0:print(json.dumps({'stage':'mst','edges_done':m,'of':n-1,'elapsed_s':round(time.time()-t1)}),flush=True)
 tree=_process_mst(mst)
 # Closing memmap and deleting temp matrix to release disk space.
 del D
 os.unlink(path)
 if debug:print(json.dumps({'stage':'mst_complete','elapsed_s':round(time.time()-t1,2)}),flush=True)
 return tree

def main():
 p=argparse.ArgumentParser();p.add_argument('--matrix',type=Path,required=True);p.add_argument('--roster',type=Path,required=True)
 p.add_argument('--view',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--min-samples',type=int,default=10)
 args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
 path=args.out/'summary.private.json'
 if path.exists():raise FileExistsError(path)
 X=np.asarray(np.load(args.matrix,mmap_mode='r'),dtype=np.float64,order='C');assert X.shape==(57204,768)
 ids=[json.loads(line)['article_id'] for line in gzip.open(args.roster,'rt')];assert len(ids)==57204 and len(set(ids))==57204
 start=time.time();tree=compute_single_linkage(X,args.out/'distance_cache.tmp',min_samples=args.min_samples,debug=True)
 print(json.dumps({'stage':'full_fit_complete','view':args.view,'elapsed_s':round(time.time()-start)}),flush=True)
 labels={};probs={};summ={}
 for threshold in (30,80,150):
  la,pr=tree_to_labels(tree,threshold,cluster_selection_method='eom',allow_single_cluster=False,cluster_selection_epsilon=0.0,max_cluster_size=None)
  la=np.asarray(la,dtype=np.int32);pr=np.asarray(pr,dtype=np.float64)
  assert len(la)==57204 and np.isfinite(pr).all() and np.all((pr>=0)&(pr<=1))
  un,counts=np.unique(la[la>=0],return_counts=True);assert np.array_equal(un,np.arange(len(un)))
  labels[str(threshold)]=la;probs[str(threshold)]=pr
  summ[str(threshold)]={'cluster_count':len(un),'assigned':int((la>=0).sum()),'noise':int((la<0).sum()),
                       'sizes_descending':sorted(map(int,counts),reverse=True),'max_probability':float(pr.max()),'min_probability':float(pr.min())}
  print(json.dumps({'stage':'threshold','view':args.view,'mcs':threshold,'clusters':len(un),'noise':summ[str(threshold)]['noise']}),flush=True)
 with open(args.out/'assignments.private.jsonl.gz','xb') as f,gzip.GzipFile(fileobj=f,mode='wb',mtime=0,filename='',compresslevel=5) as z:
  for i,aid in enumerate(ids):
   x={'article_id':aid,'node_index':i,'labels':{k:int(v[i]) if v[i]>=0 else None for k,v in labels.items()},
      'noise':{k:bool(v[i]<0) for k,v in labels.items()},'membership_strength':{k:float(v[i]) for k,v in probs.items()}}
   z.write((json.dumps(x,separators=(',',':'),sort_keys=True)+'\n').encode())
 report={'schema':'pro-adherence-stage3-full-semantic-hdbscan/v1','view':args.view,'status':'FULL_57204_EXACT_HDBSCAN_LOCAL_COMPUTED',
         'count':57204,'dimension':768,'method':'exact full float64 Euclidean distances via BLAS/disk-backed Prim mutual-reachability MST; sklearn EOM flat labels; original 768d unit vectors; no PCA/UMAP/approximate graph',
         'min_samples':args.min_samples,'min_cluster_size':[30,80,150],'fit_runtime_seconds':time.time()-start,'results':summ,
         'matrix_sha256':sha(args.matrix),'roster_sha256':sha(args.roster),'sklearn':sklearn.__version__,'numpy':np.__version__,'python':platform.python_version(),
         'note':'Non-external-scientific-validity; exact method reimplemented to remain within 4GiB RAM using disk-backed all-pair distances'}
 path.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 manifest={'schema':'pro-adherence-stage3-full-semantic-hdbscan-execution/v1','view':args.view,
   'data_paths':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in [path,args.out/'assignments.private.jsonl.gz']},
   'runner_sha256':sha(__file__),'input_matrix_sha256':sha(args.matrix),'input_roster_sha256':sha(args.roster)}
 (args.out/'manifest.private.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'stage':'done','view':args.view,'elapsed_s':round(time.time()-start)}),flush=True)
if __name__=='__main__':main()

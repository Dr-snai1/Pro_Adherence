#!/usr/bin/env python3
"""Shared deterministic random-pair cosine geometry on full source vectors.
Descriptive only. No model ranking or topic validation.
"""
import sys,hashlib,json,os
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def sha(path):
 with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main(root):
 matrices={
  'PubMedBERT CLS':root.parent/'stage3_pubmedbert_hdbscan_20261115_private/cls_unit.float32.npy',
  'PubMedBERT Mean':root.parent/'stage3_pubmedbert_hdbscan_20261115_private/mean_unit.float32.npy',
  'SPECTER2':root/'specter2_proximity_unit.float32.npy',
 }
 rng=np.random.default_rng(20261031);n=57204;size=100000
 i=rng.integers(0,n,size,dtype=np.int64);j=rng.integers(0,n,size,dtype=np.int64)
 # Avoid self-comparison by moving second endpoint one step deterministically.
 j[j==i]=(j[j==i]+1)%n
 outcome={};samples={}
 for name,p in matrices.items():
  X=np.load(p,mmap_mode='r')
  assert X.shape==(57204,768)
  sims=np.empty(size,dtype=np.float64)
  for lo in range(0,size,2500):
   hi=min(size,lo+2500)
   a=np.asarray(X[i[lo:hi]],dtype=np.float64)
   b=np.asarray(X[j[lo:hi]],dtype=np.float64)
   sims[lo:hi]=np.einsum('ij,ij->i',a,b)
  norms=[];mean=np.zeros(768,dtype=np.float64)
  for lo in range(0,n,2000):mean+=np.asarray(X[lo:lo+2000],dtype=np.float64).sum(axis=0)
  mean/=n
  outcome[name]={'source_matrix_sha':sha(p),'cosine_quantiles':dict(zip(['q01','q05','q25','q50','q75','q95','q99'],map(float,np.quantile(sims,[.01,.05,.25,.5,.75,.95,.99])))),
    'cosine_mean':float(sims.mean()),'cosine_std':float(sims.std()),'centroid_l2':float(np.linalg.norm(mean))}
  samples[name]=sims
 fig,ax=plt.subplots(figsize=(10,6),layout='constrained')
 for name in matrices:ax.hist(samples[name],bins=100,range=(-.1,1),density=True,histtype='step',linewidth=1.7,label=name)
 ax.set_xlabel('Cosine similarity of identical randomly selected article pairs');ax.set_ylabel('Density');ax.set_title('Original 768d semantic embedding geometry | full roster | 100,000 shared pairs')
 ax.legend();ax.grid(alpha=.2)
 folder=root/'figures';folder.mkdir(exist_ok=True)
 p=folder/'full_semantic_cosine_shared_pairs.png';fig.savefig(p,dpi=180);plt.close(fig)
 report={'schema':'pro-adherence-stage3-full-semantic-geometry/v1','full_n':57204,'pair_count':size,'seed':20261031,
         'selection':'shared uniform random article pairs, self pairs replaced by adjacent index',
         'views':outcome,'figure_sha256':sha(p),
         'warning':'No comparative quality inference from anisotropy or cosine distributions'}
 (root/'geometry_analytics.private.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'result':'COMPLETE','views':{k:v['cosine_quantiles']['q50'] for k,v in outcome.items()}}))
if __name__=='__main__':main(Path(sys.argv[1]))

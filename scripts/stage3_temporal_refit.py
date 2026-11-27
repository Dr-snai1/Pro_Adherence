"""Same-size exploratory re-estimation on historical and random article subsets.
HDBSCAN conditional on frozen full-corpus representations (not historical embeddings);
Leiden on induced directed citation data, with projections rebuilt inside each subset.
"""
import collections as C, concurrent.futures as cf, hashlib, json, math, multiprocessing as mp, os,random,sys,time
from pathlib import Path
import numpy as np
import sklearn
from sklearn.cluster import HDBSCAN
from sklearn.cluster._hdbscan.hdbscan import tree_to_labels
from sklearn.metrics import adjusted_rand_score
from scipy.sparse import csr_matrix,triu
from scipy.sparse.csgraph import connected_components
import igraph as ig
from stage3_temporal_fixed import load,yearrows,seed,sha,jread,write,envelope,N
from stage3_leiden_graphs import source as graph_source
CUTS=[2000,2005,2010]; REPEATS=10; GAMMA=1.; GRAPH_SEED=20261031

def digest(a):return hashlib.sha256(np.asarray(a,np.int32).tobytes()).hexdigest()
def ari(a,b):return float(adjusted_rand_score(a,b)) if len(a)>=2 else None

def describe(y,ref,graph=False):
 ready=y!=-2;assigned=y>=0;both=assigned&(ref>=0);jr=assigned|(ref>=0);same_ready=ready&(ref!=-2);c=C.Counter(int(k) for k in y if k>=0);sizes=sorted(c.values(),reverse=True);n=len(y);na=int(assigned.sum());nr=int(ready.sum());assert na+int((y==-1).sum())+int((y==-2).sum())==n and sum(sizes)==na
 return dict(n=n,ready=nr,assigned=na,noise=int((y==-1).sum()),missing_structural=n-nr,clusters=len(sizes),cluster_sizes=sizes,clusters_ge30=sum(s>=30 for s in sizes),largest_among_assigned=max(sizes,default=0)/na if na else 0.,noise_share_ready=int((y==-1).sum())/nr if nr else 0.,missing_share_all=(n-nr)/n,assigned_share_all=na/n,ari_same_ready=ari(y[same_ready],ref[same_ready]),ari_jointly_assigned=ari(y[both],ref[both]),jointly_assigned=int(both.sum()),assigned_jaccard=float(both.sum()/jr.sum()) if jr.any() else None,assignment_sha256=digest(y))

def test_hdbscan():
 rng=np.random.default_rng(4242);X=np.r_[rng.normal(0,.2,(30,3)),rng.normal(4,.2,(30,3)),rng.uniform(-6,8,(12,3))];f=HDBSCAN(min_samples=5,min_cluster_size=8,algorithm='kd_tree',n_jobs=1,copy=True).fit(X);g=HDBSCAN(min_samples=5,min_cluster_size=3,algorithm='kd_tree',n_jobs=1,copy=True).fit(X);l,_=tree_to_labels(f._single_linkage_tree_,3,'eom',False,0.,None);assert np.array_equal(l<0,g.labels_<0) and ari(l,g.labels_)==1.
 # Check that re-extraction of the fit's original threshold is byte-identical.
 l,_=tree_to_labels(f._single_linkage_tree_,8,'eom',False,0.,None);assert np.array_equal(l,f.labels_)

# Loaded once in parent, read-only forked arrays (4 concurrent bounded workers).
PARTS=None;PROJS=None;SAMPLES=None;A=None;OUT=None

def hdb_worker(view):
 p=next(p for p in PARTS if p['view']==view and p['algorithm']=='HDBSCAN');X=PROJS[view];ref=p['y'];records=[];ys={};start=time.monotonic();test_hdbscan()
 for sid,idx in SAMPLES.items():
  xx=X[idx];ready=np.isfinite(xx).all(axis=1);assert np.array_equal(ready,ref[idx]!=-2);xx=np.asarray(xx[ready],np.float64,order='C');ms=p['ms'];mcs=p['mcs'];scaled=max(2,math.ceil(mcs*len(idx)/N));assert len(xx)>max(ms,mcs)
  t=time.monotonic();fit=HDBSCAN(min_samples=ms,min_cluster_size=mcs,algorithm='kd_tree',metric='euclidean',cluster_selection_method='eom',allow_single_cluster=False,n_jobs=1,copy=True).fit(xx);fixed=fit.labels_.astype(np.int32);la,pr=tree_to_labels(fit._single_linkage_tree_,scaled,'eom',False,0.,None);assert np.all(np.isfinite(pr));same,_=tree_to_labels(fit._single_linkage_tree_,mcs,'eom',False,0.,None);assert np.array_equal(same,fixed)
  for mode,lab,threshold in [('fixed',fixed,mcs),('proportional',la,scaled)]:
   y=np.full(len(idx),-2,np.int32);y[ready]=lab;assert set(np.unique(y)).issubset(set(range(-2,len(y)))) and np.all(y[ready]>=-1);k=f'{sid}__{mode}';ys[k]=y;r=describe(y,ref[idx]);records.append(dict(sample=sid,view=view,partition=p['name'],algorithm='HDBSCAN',mode=mode,ms=ms,mcs=threshold,**r))
  if sid.endswith('_H') or sid.endswith('_R10'):print(view,sid,'seconds',round(time.monotonic()-t,2),'clusters',records[-2]['clusters'],records[-1]['clusters'],flush=True)
 dest=OUT/f'refit_{view}.private.npz';np.savez_compressed(dest,**ys);(OUT/f'refit_{view}.private.json').write_text(json.dumps({'view':view,'records':records,'assignments_sha256':sha(dest),'seconds':time.monotonic()-start},indent=2,allow_nan=False));print(view,'DONE',round(time.monotonic()-start,1),flush=True)

def graph_worker():
 records=[];ys={};start=time.monotonic();assert ig.__version__=='0.11.9';refs={g:next(p for p in PARTS if p['name']==f'Leiden-{g}-g1.0-20261031')['y'] for g in ['direct','cocitation','coupling']}
 for sid,idx in SAMPLES.items():
  sub=A[idx,:][:,idx].tocsr();n=len(idx);assert sub.shape==(n,n) and not sub.diagonal().any();t=time.monotonic()
  for graph in refs:
   if graph=='direct':B=triu(sub.maximum(sub.T),k=1,format='csr')
   elif graph=='cocitation':B=triu(sub.T@sub,k=1,format='csr')
   else:B=triu(sub@sub.T,k=1,format='csr')
   B.sort_indices();u=np.repeat(np.arange(n,dtype=np.int32),np.diff(B.indptr));v=B.indices;w=B.data;assert np.all(u<v) and np.all(w>0);active=np.unique(np.r_[u,v]);y=np.full(n,-2,np.int32);M=int(w.sum(dtype=np.int64));q=None
   if len(u):
    reverse=np.full(n,-1,np.int32);reverse[active]=np.arange(len(active));uu=reverse[u];vv=reverse[v];g=ig.Graph(n=len(active),edges=np.column_stack((uu,vv)),directed=False);g.es['weight']=w.tolist();assert g.is_simple() and g.ecount()==len(u);ig.set_random_number_generator(random.Random(GRAPH_SEED));p=g.community_leiden(objective_function='modularity',weights='weight',resolution=GAMMA,beta=.01,n_iterations=-1);lab=np.asarray(p.membership,np.int32);y[active]=lab;k=len(p);assert len(np.unique(lab))==k
    c1=y[u];c2=y[v];within=c1==c2;degree=np.bincount(c1,weights=w,minlength=k)+np.bincount(c2,weights=w,minlength=k);inside=np.bincount(c1[within],weights=w[within],minlength=k);assert degree.sum()==2*M;q=float(np.sum(inside/M-GAMMA*(degree/(2*M))**2));assert abs(q-g.modularity(lab.tolist(),weights='weight',resolution=GAMMA,directed=False))<1e-10
    C=csr_matrix((np.ones(within.sum(),np.int8),(uu[within],vv[within])),shape=(len(active),len(active)));nc,cl=connected_components(C,directed=False);assert nc==k and len(np.unique(np.c_[lab,cl],axis=0))==k
   ys[f'{sid}__{graph}']=y;r=describe(y,refs[graph][idx],graph=True);records.append(dict(sample=sid,view=graph,partition=f'Leiden-{graph}-g1.0-20261031',algorithm='Leiden',mode='rebuild',gamma=GAMMA,seed=GRAPH_SEED,edges=len(u),total_weight=M,directed_source_edges=int(sub.nnz),modularity=q,**r));assert len(active)==r['ready']==r['assigned'] and r['noise']==0
  if sid.endswith('_H') or sid.endswith('_R10'):print('graphs',sid,'seconds',round(time.monotonic()-t,2),flush=True)
 dest=OUT/'refit_graphs.private.npz';np.savez_compressed(dest,**ys);(OUT/'refit_graphs.private.json').write_text(json.dumps({'view':'graphs','records':records,'assignments_sha256':sha(dest),'seconds':time.monotonic()-start},indent=2,allow_nan=False));print('graphs DONE',round(time.monotonic()-start,1),flush=True)

def main(root,out):
 global PARTS,PROJS,SAMPLES,A,OUT
 OUT=out;assert sklearn.__version__=='1.8.0';R=yearrows(root,out);PARTS,PROJS,evidence=load(root,R,True,True);Y=np.array([r['year'] or 0 for r in R]);frame=np.flatnonzero((Y>0)&(Y<=2025));assert len(frame)==53229;SAMPLES={};sample_info=[]
 for cut in CUTS:
  hist=np.flatnonzero((Y>0)&(Y<=cut)).astype(np.int32);n=len(hist);SAMPLES[f'{cut}_H']=hist;sample_info.append(dict(sample=f'{cut}_H',cutoff=cut,kind='historical',n=n,sha256=digest(hist)))
  for rep in range(1,REPEATS+1):
   sd=seed('refit',cut,rep);rng=np.random.default_rng(sd);ix=np.sort(rng.choice(frame,n,replace=False)).astype(np.int32);assert len(np.unique(ix))==n and np.all(np.isin(ix,frame));key=f'{cut}_R{rep:02d}';SAMPLES[key]=ix;sample_info.append(dict(sample=key,cutoff=cut,kind='uniform random',n=n,seed=sd,sha256=digest(ix)))
 np.savez_compressed(out/'refit_samples.private.npz',**SAMPLES);ids,A0=graph_source(root/'STAGE3_20261111_PRIVATE_node2vec_graph.zip');index={a:i for i,a in enumerate(ids)};perm=np.array([index[r['article_id']] for r in R]);assert len(np.unique(perm))==N;A=A0[perm,:][:,perm].tocsr();assert A.nnz==328307
 (out/'refit_sampling.private.json').write_text(json.dumps(dict(schema='stage3-temporal-refit-sampling/v1',samples=sample_info,samples_npz_sha256=sha(out/'refit_samples.private.npz'),year_roster_sha256=sha(out/'publication_years.private.jsonl.gz'),frame_n=len(frame),cutoffs=CUTS,repeats=REPEATS,seed_policy='SHA256 of 20261127|refit|cutoff|rep little-endian first 8 bytes',sources=evidence,graph_sha256=sha(root/'STAGE3_20261111_PRIVATE_node2vec_graph.zip')),indent=2));print('Prepared',len(SAMPLES),'matched-size subsets; starting fits',flush=True)
 ctx=mp.get_context('fork')
 # Four workers maximum; all use one CPU thread. Start expensive node2vec first.
 with cf.ProcessPoolExecutor(max_workers=4,mp_context=ctx) as ex:
  tasks=[ex.submit(hdb_worker,x) for x in ['node2vec','CLS','Mean','SPECTER2']]+[ex.submit(graph_worker)]
  for f in cf.as_completed(tasks):f.result()
 print('all fits completed',flush=True)
if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]))

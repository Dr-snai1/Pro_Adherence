#!/usr/bin/env python3
"""Independent readback of completed UMAP/HDBSCAN runs, without cross-view comparisons.
Neighbour check: deterministic queries against the FULL source and FULL projection.
The check is a diagnostic, not an alternative fit or proof of thematic validity.
"""
import argparse, gzip, hashlib, json
from pathlib import Path
from itertools import product
import numpy as np
from sklearn.metrics import adjusted_rand_score
from threadpoolctl import threadpool_limits

N=57204
VIEWS=('pubmedbert_cls','pubmedbert_mean','specter2_proximity')
SEEDS=(20261031,20261115)
EXPECTED={'pubmedbert_cls':'1713705e982ba6a7c804be47ae7dcf21aee7e9a32fb151753c66a1e42eeb41fc','pubmedbert_mean':'54c09c019c748adf8f0a2125082c63ea56de9d98f30b82975c0c82b97a506204','specter2_proximity':'10ec4ad05e85b59e8ae204d0d0fa273537dd48dea1baf974d9cce4c08d6fff42'}
ROSTER='3435a2e83d44e42db6c0f7de685f3e1e80ca6b4762b665af2daa9eef2fc09acf'

def sha(path):
    with open(path,'rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def summary(labels, strength, title_only):
    assert labels.shape==strength.shape==title_only.shape
    assert labels.dtype.kind=='i' and np.all(labels>=-1)
    assert np.isfinite(strength).all() and np.all((strength>=0)&(strength<=1))
    assigned=labels>=0
    assert np.all(strength[~assigned]==0)
    counts=np.bincount(labels[assigned])
    assert np.all(counts>0)
    return {'clusters':int(len(counts)),'assigned':int(assigned.sum()),'noise':int((~assigned).sum()),'largest_cluster':int(counts.max(initial=0)), 'title_only_assigned':int((title_only&assigned).sum()),'title_only_noise':int((title_only&~assigned).sum()),'cluster_sizes':sorted(counts.tolist(),reverse=True)}

def full_knn_overlap(x,y,seed,k=15,count=800):
    assert len(x)==len(y) and 0<k<len(x) and count<=len(x)
    # Recompute cosine from float64 vectors rather than assume exact unit norms.
    a=np.asarray(x,dtype=np.float64); b=np.asarray(y,dtype=np.float64)
    a/=np.linalg.norm(a,axis=1)[:,None]
    bnorm=np.einsum('ij,ij->i',b,b)
    queries=np.sort(np.random.default_rng(seed+999).choice(len(a),size=count,replace=False))
    totals=[]; ties=[0,0]
    with threadpool_limits(limits=2):
        for start in range(0,count,16):
            q=queries[start:start+16]
            scores=[-(a[q]@a.T),bnorm[q,None]+bnorm[None,:]-2*(b[q]@b.T)]
            ranks=[]
            for j,d in enumerate(scores):
                d[np.arange(len(q)),q]=np.inf
                # Stable article-index tie break; count exact ties at k boundary.
                ids=np.argsort(d,axis=1,kind='stable')[:,:k+1]
                vals=np.take_along_axis(d,ids,axis=1)
                ties[j]+=int((vals[:,k-1]==vals[:,k]).sum())
                ranks.append(ids[:,:k])
            totals.extend(len(set(l)&set(r))/k for l,r in zip(*ranks))
    return {'query_count':count,'candidate_count':len(a),'k':k,'query_seed':seed+999,'shared_neighbor_fraction':float(np.mean(totals)),'exact_ties_at_k_boundary':{'source':ties[0],'projection':ties[1]},'scope':'same-view exact diagnostic, all candidates, not thematic validation'}

def audit(base,roster,neighbors=True):
    assert sha(roster)==ROSTER
    rows=[json.loads(l) for l in gzip.open(roster,'rt')]; assert len(rows)==N and len({r['article_id'] for r in rows})==N
    title=np.array([r['text_state']=='title_only' for r in rows]); results=[]; labelsets={}; missing=[]
    for i,(view,dim,k,seed) in enumerate(product(VIEWS,(10,50),(30,100),SEEDS)):
        path=base/'runs'/f'{view}_d{dim}_k{k}_s{seed}'
        proj=path/'projection.float32.npy'; report=path/'umap_report.json'
        if not proj.exists() or not report.exists(): missing.append(i); continue
        meta=json.loads(report.read_text()); config={'index':i,'view':view,'n_components':dim,'n_neighbors':k,'seed':seed,'min_dist':0.0,'input_metric':'cosine','output_metric':'euclidean'}
        assert meta['config']==config and meta['n']==N and meta['source_sha256']==EXPECTED[view] and sha(proj)==meta['projection_sha256']
        assert meta['umap_version']=='0.5.9.post2' and meta['pynndescent_version']=='0.5.13'
        src=base/f'{view}_unit.float32.npy'; assert sha(src)==EXPECTED[view]
        x=np.load(src,mmap_mode='r',allow_pickle=False); y=np.load(proj,allow_pickle=False)
        assert x.shape==(N,768) and y.shape==(N,dim) and y.dtype==np.float32 and np.isfinite(y).all()
        entry={'config':config,'projection_sha256':sha(proj),'partitions':[]}
        if neighbors:entry['full_candidate_knn_diagnostic']=full_knn_overlap(x,y,seed)
        for ms in (5,10):
            f=path/f'hdbscan_ms{ms}.npz'; m=path/f'hdbscan_ms{ms}.json'
            if not f.exists() or not m.exists():continue
            mm=json.loads(m.read_text()); assert mm['status']=='COMPLETE' and mm['config']==config and mm['min_samples']==ms and mm['min_cluster_size']==[30,80,150]
            assert sha(f)==mm['assignments_sha256'] and mm['projection_sha256']==sha(proj)
            with np.load(f,allow_pickle=False) as z:
                required=set()
                for mcs in (30,80,150):
                    lk=f'eom_labels_{mcs}'; pk=f'eom_strength_{mcs}'; required.update([lk,pk]); labels=z[lk]; p=z[pk]; assert labels.shape==(N,)
                    s=summary(labels,p,title); ref=mm['result_summary'][str(mcs)]; assert all(ref[x]==s[x] for x in ('clusters','assigned','noise','largest_cluster'))
                    # Integer inequality is independent of the runner's floating division.
                    leaf=1<=s['clusters']<=3 and s['assigned']>0 and 4*s['largest_cluster']>=3*s['assigned']; assert ref['leaf_triggered']==leaf
                    result={'min_samples':ms,'min_cluster_size':mcs,'eom':s,'leaf_triggered':leaf}
                    labelsets[(view,dim,k,ms,mcs,seed)]=labels.copy()
                    if leaf:
                        a=f'leaf_labels_{mcs}'; b=f'leaf_strength_{mcs}';required.update([a,b]); ls=summary(z[a],z[b],title);assert ls['clusters']==ref['leaf_clusters'] and ls['noise']==ref['leaf_noise'];result['leaf']=ls
                    entry['partitions'].append(result)
                assert set(z.files)==required
        results.append(entry)
    stability=[]
    for (view,d,k,ms,mcs,seed),a in labelsets.items():
        if seed!=SEEDS[0]:continue
        b=labelsets.get((view,d,k,ms,mcs,SEEDS[1]))
        if b is None:continue
        both=(a>=0)&(b>=0)
        stability.append({'view':view,'n_components':d,'n_neighbors':k,'min_samples':ms,'min_cluster_size':mcs,'seed_ari_all':float(adjusted_rand_score(a,b)),'both_assigned':int(both.sum()),'seed_ari_both_assigned':float(adjusted_rand_score(a[both],b[both])) if both.sum()>1 else None})
    return {'schema':'stage3-umap-hdbscan-independent-audit/v1','roster_sha256':ROSTER,'projections_verified':len(results),'eom_partitions_verified':sum(len(e['partitions']) for e in results),'conditional_leaf_verified':sum(p['leaf_triggered'] for e in results for p in e['partitions']),'missing_projection_indices':missing,'results':results,'within_view_seed_stability':stability,'thematic_validity_claimed':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--roster',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    result=audit(args.base,args.roster)
    with open(args.out,'x') as f:json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('results','within_view_seed_stability')},sort_keys=True))
if __name__=='__main__':main()

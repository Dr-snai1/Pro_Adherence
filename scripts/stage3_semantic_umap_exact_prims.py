#!/usr/bin/env python3
"""Exact, bounded-memory HDBSCAN for an already verified full UMAP projection.
Uses sklearn 1.8.0 implicit Prim MST and exact KDTree core distances. This is
an implementation alternative to the disk-backed exact float64 distance MST,
not an approximate graph or change of the owner-approved scientific grid.
"""
import argparse,json,time
from pathlib import Path
import numpy as np
import sklearn
from sklearn.cluster._hdbscan.hdbscan import _hdbscan_prims,tree_to_labels
from threadpoolctl import threadpool_limits
from stage3_semantic_umap_hdbscan import N,EXPECTED,config_grid,MCS,MIN_SAMPLES,sha,write_json,should_use_leaf

def compute_tree(y,ms):
    assert sklearn.__version__=='1.8.0' and y.dtype==np.float64 and np.isfinite(y).all()
    with threadpool_limits(limits=2):
        return _hdbscan_prims(y,algo='kd_tree',min_samples=ms,alpha=1.0,metric='euclidean',leaf_size=40,n_jobs=2)

def fit_existing(base,config,ms):
    assert ms in MIN_SAMPLES
    work=base/'runs'/f"{config['view']}_d{config['n_components']}_k{config['n_neighbors']}_s{config['seed']}"
    output=work/'projection.float32.npy'; report=json.loads((work/'umap_report.json').read_text())
    assert report['config']==config and report['n']==N and report['source_sha256']==EXPECTED[config['view']]
    assert sha(base/f"{config['view']}_unit.float32.npy")==EXPECTED[config['view']]
    assert sha(output)==report['projection_sha256']
    y=np.asarray(np.load(output,allow_pickle=False),dtype=np.float64,order='C')
    assert y.shape==(N,config['n_components'])
    target=work/f'hdbscan_ms{ms}.npz'; manifest=work/f'hdbscan_ms{ms}.json'
    if target.exists() or manifest.exists():raise FileExistsError('No overwrite of existing output')
    print(json.dumps({'event':'exact_prims_start','config_index':config['index'],'ms':ms}),flush=True)
    tic=time.time();tree=compute_tree(y,ms);del y
    print(json.dumps({'event':'exact_prims_tree_complete','elapsed_seconds':time.time()-tic,'ms':ms}),flush=True)
    arrays={};summary={}
    for mcs in MCS:
        labels,prob=tree_to_labels(tree,mcs,cluster_selection_method='eom',allow_single_cluster=False,cluster_selection_epsilon=0,max_cluster_size=None)
        labels=np.asarray(labels,dtype=np.int32);prob=np.asarray(prob,dtype=np.float32)
        assert labels.shape==prob.shape==(N,) and np.isfinite(prob).all() and np.all((prob>=0)&(prob<=1))
        sizes=np.bincount(labels[labels>=0]);num=len(sizes);assigned=int((labels>=0).sum());largest=int(sizes.max(initial=0))
        leaf=should_use_leaf(num,assigned,largest)
        summary[str(mcs)]={'clusters':num,'assigned':assigned,'noise':N-assigned,'largest_cluster':largest,'leaf_triggered':leaf}
        arrays[f'eom_labels_{mcs}']=labels;arrays[f'eom_strength_{mcs}']=prob
        if leaf:
            ll,lp=tree_to_labels(tree,mcs,cluster_selection_method='leaf',allow_single_cluster=False,cluster_selection_epsilon=0,max_cluster_size=None)
            ll=np.asarray(ll,dtype=np.int32);lp=np.asarray(lp,dtype=np.float32)
            assert ll.shape==lp.shape==(N,) and np.isfinite(lp).all() and np.all((lp>=0)&(lp<=1))
            arrays[f'leaf_labels_{mcs}']=ll;arrays[f'leaf_strength_{mcs}']=lp
            summary[str(mcs)].update(leaf_clusters=int(len(np.unique(ll[ll>=0]))),leaf_noise=int((ll<0).sum()))
    with open(target,'xb') as fp:np.savez_compressed(fp,**arrays)
    write_json(manifest,{'schema':'stage3-umap-hdbscan/v1','status':'COMPLETE','config':config,'min_samples':ms,'min_cluster_size':list(MCS),'method':'exact full implicit Prim float64 Euclidean HDBSCAN; exact KDTree core distances, no pruning/approximation','backend':'sklearn._hdbscan_prims/1.8.0','cluster_selection_method':'eom; leaf only if EOM <=3 groups and largest >=75% assigned','projection_sha256':sha(output),'assignments_sha256':sha(target),'elapsed_seconds':time.time()-tic,'result_summary':summary,'note':'no inter-view comparisons, no theme labels and no quality rankings'})
    print(json.dumps({'event':'hdbscan_complete','config_index':config['index'],'ms':ms,'results':summary}),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--index',type=int,required=True);p.add_argument('--min-samples',type=int,choices=MIN_SAMPLES,required=True);a=p.parse_args();fit_existing(a.base,config_grid()[a.index],a.min_samples)
if __name__=='__main__':main()

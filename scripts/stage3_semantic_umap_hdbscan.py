#!/usr/bin/env python3
"""Owner-authorized Stage 3 UMAP->HDBSCAN experiment, full frozen cohort.

3 independent input views (PubMedBERT CLS / Mean, SPECTER2 proximity), two
UMAP dimensions (10,50), two n_neighbors (30,100), two seeds, 2 HDBSCAN
min_samples (5,10), 3 min_cluster_size (30,80,150). No cross-view comparisons.

Do not confuse UMAP mapping, which is stochastic and uses approximate neighbour
search, with the exact 768d HDBSCAN baseline. Never change frozen inputs.

Usage:
 python stage3_semantic_umap_hdbscan.py --preflight-only --base /mnt/data/stage3_umap_hdbscan_20261127_private
 python stage3_semantic_umap_hdbscan.py --all --base /mnt/data/stage3_umap_hdbscan_20261127_private
 or --index 0 ... --index 23. Restart skips only fully manifest-verified outputs.

Requires umap-learn==0.5.9.post2 and pynndescent==0.5.13, NumPy==2.3.5,
SciPy==1.17.0, scikit-learn==1.8.0, numba==0.65.1, plus the existing
`stage3_full_semantic_hdbscan_dense_exact.py` module on PYTHONPATH.
"""
from __future__ import annotations
import argparse,hashlib,json,os,sys,time,platform,importlib
from importlib.metadata import version as package_version
from pathlib import Path
from itertools import product
import numpy as np
from threadpoolctl import threadpool_limits

N=57204; DIM=768
SEEDS=(20261031,20261115)
VIEWS=('pubmedbert_cls','pubmedbert_mean','specter2_proximity')
DIMS=(10,50)
NEIGHBORS=(30,100)
MIN_SAMPLES=(5,10)
MCS=(30,80,150)
EXPECTED={
 'pubmedbert_cls':'1713705e982ba6a7c804be47ae7dcf21aee7e9a32fb151753c66a1e42eeb41fc',
 'pubmedbert_mean':'54c09c019c748adf8f0a2125082c63ea56de9d98f30b82975c0c82b97a506204',
 'specter2_proximity':'10ec4ad05e85b59e8ae204d0d0fa273537dd48dea1baf974d9cce4c08d6fff42'
}

def config_grid():
    return [{'index':i,'view':view,'n_components':nd,'n_neighbors':nn,'seed':seed,
             'min_dist':0.0,'input_metric':'cosine','output_metric':'euclidean'}
            for i,(view,nd,nn,seed) in enumerate(product(VIEWS,DIMS,NEIGHBORS,SEEDS))]

def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def secure_dir(p):p.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(p,0o700)

def write_json(p,d):
    if p.exists():raise FileExistsError(p)
    p.write_text(json.dumps(d,sort_keys=True,indent=2,allow_nan=False)+'\n')
    os.chmod(p,0o600)

def env_check():
    requirements={'numpy':'2.3.5','scipy':'1.17.0','sklearn':'1.8.0',
                  'numba':'0.65.1','umap':'0.5.9.post2','pynndescent':'0.5.13'}
    found={};bad=[]
    for mod,expected in requirements.items():
        try:
            module=importlib.import_module(mod)
            if mod=='umap':
                got=package_version('umap-learn')
            else:got=getattr(module,'__version__','unknown')
            found[mod]=got
            if got!=expected:bad.append(f'{mod}: expected {expected}, found {got}')
        except Exception as e:
            found[mod]=f'MISSING: {type(e).__name__}: {str(e)[:100]}'
            bad.append(f'{mod} missing')
    try:
        from stage3_full_semantic_hdbscan_dense_exact import compute_single_linkage
        found['exact_hdbscan_runner']=sha(Path(importlib.import_module('stage3_full_semantic_hdbscan_dense_exact').__file__))
    except Exception as e:
        bad.append(f'exact HDBSCAN runner missing: {type(e).__name__}: {e}')
    return {'found':found,'missing_or_mismatch':bad}

def knn_preservation(full_source,projection,seed,k=15,count=800):
    """Diagnostic only: within deterministic 800-paper subset; NOT a substitute for full fit."""
    from sklearn.neighbors import NearestNeighbors
    rng=np.random.default_rng(seed+999);s=np.sort(rng.choice(len(full_source),size=count,replace=False))
    original=full_source[s];embedded=projection[s]
    with threadpool_limits(limits=2):
        left=NearestNeighbors(n_neighbors=k+1,algorithm='brute',metric='cosine',n_jobs=2).fit(original).kneighbors(original,return_distance=False)
        right=NearestNeighbors(n_neighbors=k+1,algorithm='brute',metric='euclidean',n_jobs=2).fit(embedded).kneighbors(embedded,return_distance=False)
    # The first neighbor is typically self, but explicitly remove it to avoid ambiguity.
    fractions=[]
    for i in range(count):
        a=[j for j in left[i] if j!=i][:k]
        b=[j for j in right[i] if j!=i][:k]
        fractions.append(len(set(a)&set(b))/k)
    return {'sample_size':count,'neighbor_k':k,'sample_seed':seed+999,
            'shared_neighbours_fraction':float(np.mean(fractions)),
            'scope':'sample diagnostic only; all UMAP and HDBSCAN fits use full 57,204'}

def should_use_leaf(cluster_count, assigned, largest):
    """Owner-approved conditional leaf extraction for a few oversized EOM groups."""
    return bool(1<=cluster_count<=3 and assigned>0 and largest/assigned>=0.75)

def fit_one(base,config,umap_only=False):
    from umap import UMAP
    from sklearn.cluster._hdbscan.hdbscan import tree_to_labels
    from stage3_full_semantic_hdbscan_dense_exact import compute_single_linkage
    work=base/'runs'/f"{config['view']}_d{config['n_components']}_k{config['n_neighbors']}_s{config['seed']}"
    secure_dir(work)
    filename=base/f"{config['view']}_unit.float32.npy"
    if sha(filename)!=EXPECTED[config['view']]:raise ValueError('Frozen source SHA mismatch')
    X=np.load(filename,mmap_mode='r')
    if X.shape!=(N,DIM) or X.dtype!=np.float32:raise ValueError('Input mismatch')
    output=work/'projection.float32.npy'
    umeta=work/'umap_report.json'
    if output.exists() and umeta.exists():
        R=json.loads(umeta.read_text())
        if R['projection_sha256']!=sha(output):raise ValueError('Existing projection SHA mismatch; no silent overwrites')
        Y=np.load(output,mmap_mode='r')
        assert Y.shape==(N,config['n_components'])
    elif output.exists() or umeta.exists():
        raise FileExistsError('Partial UMAP output; inspect/repair instead of overwriting')
    else:
        print(json.dumps({'event':'umap_fit_start','config':config}),flush=True)
        start=time.time()
        mapper=UMAP(n_neighbors=config['n_neighbors'],n_components=config['n_components'],min_dist=0.0,
                    metric='cosine',random_state=config['seed'],transform_seed=config['seed'],n_jobs=1,
                    init='spectral',low_memory=True,densmap=False)
        with threadpool_limits(limits=2):Y=mapper.fit_transform(X)
        assert Y.shape==(N,config['n_components']) and np.isfinite(Y).all()
        Y=np.asarray(Y,dtype=np.float32)
        with open(output,'xb') as fp:np.save(fp,Y)
        os.chmod(output,0o600)
        report={'schema':'stage3-umap-projection/v1','config':config,'n':N,'source_sha256':EXPECTED[config['view']],
                'projection_sha256':sha(output),'elapsed_seconds':time.time()-start,
                'umap_version':package_version('umap-learn'),
                'pynndescent_version':package_version('pynndescent'),
                'python':platform.python_version(),'numpy':np.__version__,
                'neighborhood_preservation':knn_preservation(X,Y,config['seed']),
                'warning':'UMAP approximate kNN and density-distorting layout; do not interpret lower noise as validation'}
        write_json(umeta,report)
        print(json.dumps({'event':'umap_fit_complete','config_index':config['index'],'sha':sha(output)}),flush=True)
    if umap_only:return
    for ms in MIN_SAMPLES:
        target=work/f'hdbscan_ms{ms}.npz';manifest=work/f'hdbscan_ms{ms}.json'
        if target.exists() and manifest.exists():
            if json.loads(manifest.read_text())['assignments_sha256']!=sha(target):raise ValueError('HDBSCAN output SHA mismatch')
            continue
        if target.exists() or manifest.exists():raise FileExistsError('Incomplete HDBSCAN run')
        tic=time.time()
        # Exact full n*n distances, disk-backed. 26.2 GB scratch file is cleaned on success.
        Z=np.asarray(np.load(output,mmap_mode='r'),dtype=np.float64,order='C')
        with threadpool_limits(limits=2):
            tree=compute_single_linkage(Z,work/f'distance_cache_ms{ms}.tmp',min_samples=ms,block=128,debug=True)
        del Z
        arrays={};summary={}
        for mcs in MCS:
            labels,prob=tree_to_labels(tree,mcs,cluster_selection_method='eom',allow_single_cluster=False,
                                     cluster_selection_epsilon=0,max_cluster_size=None)
            labels=np.asarray(labels,dtype=np.int32);prob=np.asarray(prob,dtype=np.float32)
            assert len(labels)==N and len(prob)==N and np.isfinite(prob).all() and np.all((prob>=0)&(prob<=1))
            num=int(len(np.unique(labels[labels>=0])));assigned=int(np.sum(labels>=0))
            sizes=np.unique(labels[labels>=0],return_counts=True)[1]
            largest=int(sizes.max()) if len(sizes) else 0
            summary[str(mcs)]={'clusters':num,'assigned':assigned,'noise':N-assigned,'largest_cluster':largest}
            arrays[f'eom_labels_{mcs}']=labels
            arrays[f'eom_strength_{mcs}']=prob
            # Approved conditional branch: few large clusters, objectively defined.
            leaf_trigger=should_use_leaf(num,assigned,largest)
            summary[str(mcs)]['leaf_triggered']=leaf_trigger
            if leaf_trigger:
                leaf_l,leaf_p=tree_to_labels(tree,mcs,cluster_selection_method='leaf',allow_single_cluster=False,
                                             cluster_selection_epsilon=0,max_cluster_size=None)
                leaf_l=np.asarray(leaf_l,dtype=np.int32);leaf_p=np.asarray(leaf_p,dtype=np.float32)
                arrays[f'leaf_labels_{mcs}']=leaf_l; arrays[f'leaf_strength_{mcs}']=leaf_p
                summary[str(mcs)]['leaf_clusters']=int(len(np.unique(leaf_l[leaf_l>=0])))
                summary[str(mcs)]['leaf_noise']=int((leaf_l<0).sum())
        with open(target,'xb') as fp:np.savez_compressed(fp,**arrays)
        os.chmod(target,0o600)
        write_json(manifest,{'schema':'stage3-umap-hdbscan/v1','status':'COMPLETE','config':config,
                            'min_samples':ms,'min_cluster_size':list(MCS),'method':'exact full disk-backed 57,204-row HDBSCAN',
                            'cluster_selection_method':'eom; leaf only if EOM <=3 groups and largest >=75% assigned',
                            'projection_sha256':sha(output),'assignments_sha256':sha(target),
                            'elapsed_seconds':time.time()-tic,'result_summary':summary,
                            'note':'no inter-view comparisons, no theme labels and no quality rankings'})
        print(json.dumps({'event':'hdbscan_complete','config_index':config['index'],'ms':ms,'results':summary}),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',type=Path,required=True)
    selector=parser.add_mutually_exclusive_group(required=True)
    selector.add_argument('--all',action='store_true');selector.add_argument('--index',type=int)
    selector.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--umap-only',action='store_true',help='Only create or verify UMAP projection; run exact Prim backend separately')
    args=parser.parse_args();os.umask(0o077)
    grid=config_grid()
    preflight={'schema':'stage3-umap-hdbscan-runtime-preflight/v1','full_cohort':N,'umap_fits':len(grid),
               'eom_partitions':len(grid)*len(MIN_SAMPLES)*len(MCS),'approved_grid':grid,
               'leaf_rule':'1-3 EOM clusters; largest covers at least 75% of assigned at same threshold',
               'dependencies':env_check()}
    for view in VIEWS:
        p=args.base/f'{view}_unit.float32.npy'
        preflight.setdefault('inputs',{})[view]={
            'exists':p.exists(), 'sha256':sha(p) if p.exists() else None,
            'expected_sha256':EXPECTED[view]}
    if args.preflight_only:
        print(json.dumps(preflight,sort_keys=True,indent=2));return
    if preflight['dependencies']['missing_or_mismatch']:
        raise RuntimeError('Pinned UMAP dependencies unavailable: '+str(preflight['dependencies']['missing_or_mismatch']))
    if not all(v['sha256']==v['expected_sha256'] for v in preflight['inputs'].values()):
        raise RuntimeError('Frozen inputs missing or not identical')
    selected=grid if args.all else [grid[args.index]]
    for config in selected:fit_one(args.base,config,umap_only=args.umap_only)
    print(json.dumps({'status':'selected_umap_complete' if args.umap_only else 'all_selected_runs_complete','selected':[v['index'] for v in selected]}),flush=True)
if __name__=='__main__':main()

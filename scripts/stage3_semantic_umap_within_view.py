#!/usr/bin/env python3
"""Full-grid, single-view sensitivity diagnostics from existing verified EOM labels.
No refits, cross-view comparisons, rankings or thematic validity claims.
Each pair differs in exactly one specified factor. Noise is a single category for
all-row ARI; also report ARI on the intersection of assigned rows and its size.
"""
import argparse, gzip, json, math
from itertools import combinations
from pathlib import Path
import numpy as np
from sklearn.metrics import adjusted_rand_score
from stage3_semantic_umap_hdbscan import config_grid, EXPECTED, N, sha
from stage3_semantic_umap_audit import ROSTER, summary

FACTORS=('n_components','n_neighbors','seed','min_samples','min_cluster_size')

def ari_exact(a,b):
    n=len(a)
    if n<2:return None
    _,ai=np.unique(a,return_inverse=True);_,bi=np.unique(b,return_inverse=True)
    ca=np.bincount(ai);cb=np.bincount(bi);ct=np.bincount(ai*len(cb)+bi)
    choose2=lambda x: sum(int(v)*(int(v)-1)//2 for v in x)
    A=choose2(ca);B=choose2(cb);C=choose2(ct);T=n*(n-1)//2
    den=(A+B)*T-2*A*B
    return 1.0 if den==0 else (2*C*T-2*A*B)/den

def checked_ari(a,b):
    v=ari_exact(a,b)
    if v is not None:assert math.isclose(v,adjusted_rand_score(a,b),rel_tol=1e-12,abs_tol=1e-12)
    return v

def analyze(base,roster,view):
    assert sha(roster)==ROSTER
    rows=[json.loads(r) for r in gzip.open(roster,'rt')]
    assert len(rows)==N and len({r['article_id'] for r in rows})==N
    title=np.array([r['text_state']=='title_only' for r in rows]); n_title=int(title.sum())
    assert set(r['text_state'] for r in rows)=={'title_only','title_abstract'}
    assert sha(base/f'{view}_unit.float32.npy')==EXPECTED[view]
    results=[];labels={};leaves=0
    for cfg in config_grid():
        if cfg['view']!=view:continue
        path=base/'runs'/f"{view}_d{cfg['n_components']}_k{cfg['n_neighbors']}_s{cfg['seed']}"
        p=path/'projection.float32.npy'; pr=json.loads((path/'umap_report.json').read_text())
        assert pr['config']==cfg and pr['source_sha256']==EXPECTED[view] and sha(p)==pr['projection_sha256']
        for ms in (5,10):
            f=path/f'hdbscan_ms{ms}.npz'; meta=json.loads((path/f'hdbscan_ms{ms}.json').read_text())
            assert meta['config']==cfg and meta['status']=='COMPLETE' and meta['min_samples']==ms and meta['projection_sha256']==sha(p) and meta['assignments_sha256']==sha(f)
            with np.load(f,allow_pickle=False) as z:
                for mcs in (30,80,150):
                    a=z[f'eom_labels_{mcs}']; q=z[f'eom_strength_{mcs}']; s=summary(a,q,title); assert len(a)==N
                    ref=meta['result_summary'][str(mcs)];assert all(s[k]==ref[k] for k in ('clusters','assigned','noise','largest_cluster'))
                    key=(cfg['n_components'],cfg['n_neighbors'],cfg['seed'],ms,mcs);labels[key]=a.copy()
                    def coverage(s):
                        return {'title_only_noise':s['title_only_noise'],'title_only_total':n_title,'title_only_noise_fraction':s['title_only_noise']/n_title,'title_abstract_noise':s['noise']-s['title_only_noise'],'title_abstract_total':N-n_title,'title_abstract_noise_fraction':(s['noise']-s['title_only_noise'])/(N-n_title)}
                    rec={'parameters':dict(zip(FACTORS,key)),'config_index':cfg['index'],'projection_sha256':pr['projection_sha256'],'assignments_sha256':meta['assignments_sha256'],'eom':s,'text_coverage':coverage(s)}
                    trigger=1<=s['clusters']<=3 and s['assigned']>0 and 4*s['largest_cluster']>=3*s['assigned'];assert trigger==ref['leaf_triggered'];rec['leaf_triggered']=trigger
                    if trigger:
                        ss=summary(z[f'leaf_labels_{mcs}'],z[f'leaf_strength_{mcs}'],title);assert ss['clusters']==ref['leaf_clusters'] and ss['noise']==ref['leaf_noise'];rec['leaf']=ss;rec['leaf_text_coverage']=coverage(ss);leaves+=1
                    results.append(rec)
    assert len(labels)==48 and len(results)==48
    pairs=[]
    for (ka,a),(kb,b) in combinations(labels.items(),2):
        changes=[i for i,(x,y) in enumerate(zip(ka,kb)) if x!=y]
        if len(changes)!=1:continue
        aa=a>=0;bb=b>=0;both=aa&bb;union=aa|bb
        pairs.append({'changed_factor':FACTORS[changes[0]],'a':dict(zip(FACTORS,ka)),'b':dict(zip(FACTORS,kb)),'ari_all':checked_ari(a,b),'both_assigned':int(both.sum()),'ari_both_assigned':checked_ari(a[both],b[both]),'both_noise':int((~union).sum()),'assigned_a_only':int((aa&~bb).sum()),'assigned_b_only':int((bb&~aa).sum()),'assigned_jaccard':float(both.sum()/union.sum()) if union.any() else None})
    counts={f:sum(p['changed_factor']==f for p in pairs) for f in FACTORS}
    assert counts=={'n_components':24,'n_neighbors':24,'seed':24,'min_samples':24,'min_cluster_size':48}
    for p in pairs:assert p['both_assigned']+p['both_noise']+p['assigned_a_only']+p['assigned_b_only']==N
    return {'schema':'stage3-umap-within-view-sensitivity/v1','view':view,'source_sha256':EXPECTED[view],'roster_sha256':ROSTER,'n':N,'projections':8,'eom_partitions':48,'conditional_leaf_partitions':leaves,'single_factor_pair_counts':counts,'ari_check':'independent exact integer contingency formula equals sklearn for all reported ARI values','partition_diagnostics':results,'single_factor_eom_pairs':pairs,'limitations':'EOM all-grid comparison only within this view. Conditional leaf coverage described separately; no leaf-vs-EOM or cross-view ranking. Noise is one category in all-row ARI; intersection-only ARI reports selected denominator. No thematic validity claimed.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--roster',type=Path,required=True);p.add_argument('--view',choices=tuple(EXPECTED),required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=analyze(a.base,a.roster,a.view)
    with open(a.out,'x') as f:json.dump(r,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    a.out.chmod(0o600)
    print(json.dumps({k:r[k] for k in ('view','n','projections','eom_partitions','conditional_leaf_partitions','single_factor_pair_counts')},sort_keys=True));print('sha256',sha(a.out))
if __name__=='__main__':main()

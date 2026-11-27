#!/usr/bin/env python3
"""Deterministic single-view content spot-check roster, not a new clustering fit.
Fixed diagnostic threshold: min_samples=10, min_cluster_size=80, all eight UMAP
settings, EOM plus leaf only if already triggered at that threshold. Up to three
records from largest and smallest distinct cluster and from noise. No best-run
selection, no external validation, no cross-view comparisons.
"""
import argparse,gzip,hashlib,json,zipfile
from pathlib import Path
import numpy as np
from stage3_semantic_umap_hdbscan import config_grid,EXPECTED,N,sha
from stage3_semantic_umap_audit import ROSTER
SOURCE_ZIP='cc60cefdaa62a60712425b0f1ea1719338ec4250ec8bcaf1fd465329c677395e'
SOURCE_GZIP='1611f07e18ccf999493938e552d1a73ad049db931a11399fc01f0ca7b07dc053'
SELECTION_SEED=20261127

def select(base,roster_path,source_path,view):
    assert sha(roster_path)==ROSTER and sha(source_path)==SOURCE_ZIP
    roster=[json.loads(l) for l in gzip.open(roster_path,'rt')];assert len(roster)==N and len({r['article_id'] for r in roster})==N
    groups=[];selected=set()
    for cfg in config_grid():
        if cfg['view']!=view:continue
        path=base/'runs'/f"{view}_d{cfg['n_components']}_k{cfg['n_neighbors']}_s{cfg['seed']}"
        proj=path/'projection.float32.npy'; f=path/'hdbscan_ms10.npz'; meta=json.loads((path/'hdbscan_ms10.json').read_text())
        assert meta['config']==cfg and meta['min_samples']==10 and meta['status']=='COMPLETE' and sha(f)==meta['assignments_sha256'] and sha(proj)==meta['projection_sha256']
        with np.load(f,allow_pickle=False) as z:
            for method in ('eom','leaf'):
                key=f'{method}_labels_80';trigger=meta['result_summary']['80']['leaf_triggered']
                if method=='leaf' and not trigger:assert key not in z;continue
                labels=z[key];assert labels.shape==(N,) and np.all(labels>=-1)
                ids,counts=np.unique(labels[labels>=0],return_counts=True)
                ranks=sorted(zip(map(int,ids),map(int,counts)),key=lambda x:(-x[1],x[0]))
                strata=[]
                if ranks:strata.append(('largest_cluster',*ranks[0]))
                if len(ranks)>1:strata.append(('smallest_cluster',*ranks[-1]))
                noise=int((labels==-1).sum())
                if noise:strata.append(('noise',-1,noise))
                for stratum,label,size in strata:
                    members=np.flatnonzero(labels==label);assert len(members)==size
                    def rank(i):
                        aid=roster[int(i)]['article_id']
                        return (hashlib.sha256(f'{SELECTION_SEED}|{cfg["index"]}|{method}|{label}|{aid}'.encode()).digest(),int(i))
                    sample=sorted(members,key=rank)[:3];indices=[int(i) for i in sample]
                    selected.update(indices);groups.append({'config':cfg,'method':method,'min_samples':10,'min_cluster_size':80,'stratum':stratum,'cluster_label':label,'stratum_size':size,'assignment_sha256':meta['assignments_sha256'],'sample_row_indices':indices})
    assert len({g['config']['index'] for g in groups})==8
    with zipfile.ZipFile(source_path) as z:
        assert z.testzip() is None
        with z.open('full_pubmedbert_inputs.private.jsonl.gz') as f:
            assert hashlib.file_digest(f,'sha256').hexdigest()==SOURCE_GZIP
        source={};count=0
        with z.open('full_pubmedbert_inputs.private.jsonl.gz') as raw,gzip.GzipFile(fileobj=raw) as f:
            for i,line in enumerate(f):
                r=json.loads(line);assert r['article_id']==roster[i]['article_id'] and r['text_state']==roster[i]['text_state'];count+=1
                if i in selected:source[i]={'article_id':r['article_id'],'text_state':r['text_state'],'title':r['title'],'abstract':r['abstract']}
    assert count==N and set(source)==selected
    for g in groups:g['sample']=[dict(row_index=i,**source[i]) for i in g['sample_row_indices']]
    return {'schema':'stage3-umap-content-spotcheck-roster/v1','status':'SAMPLE_SELECTED__NOT_YET_REVIEWED','view':view,'source_zip_sha256':SOURCE_ZIP,'source_gzip_sha256':SOURCE_GZIP,'roster_sha256':ROSTER,'selection_seed':SELECTION_SEED,'fixed_diagnostic_threshold':{'min_samples':10,'min_cluster_size':80},'sample_scheme':'Each existing EOM and eligible leaf at fixed threshold; largest and smallest distinct cluster by size, and noise if present, 3 per stratum using SHA256 deterministic ranking. No fit subsampling. Not representative of all clusters or thresholds.','groups':groups,'sample_occurrences':sum(len(g['sample']) for g in groups),'unique_article_count':len(selected),'source_roster_match_all_rows':True}

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--roster',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--view',choices=tuple(EXPECTED),required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=select(a.base,a.roster,a.source,a.view)
    with open(a.out,'x') as f:json.dump(r,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
    a.out.chmod(0o600);print(json.dumps({k:r[k] for k in ('view','status','sample_occurrences','unique_article_count','source_roster_match_all_rows')},sort_keys=True));print('sha256',sha(a.out))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Full-grid integrity acceptance from previously fetched restricted checkpoints.
No fitting, cross-view comparison, or claim of scientific thematic validity.
Evidence index is private and supplied separately; hashes must be verified.
"""
import argparse,hashlib,json,zipfile
from pathlib import Path
from collections import Counter
from stage3_semantic_umap_hdbscan import config_grid,EXPECTED,N,sha
from stage3_semantic_umap_audit import audit,ROSTER

RUN_FILES={'projection.float32.npy','umap_report.json','hdbscan_ms5.npz','hdbscan_ms5.json','hdbscan_ms10.npz','hdbscan_ms10.json'}

def bytesha(b): return hashlib.sha256(b).hexdigest()

def checked_file(root,rec):
    p=root/rec['name'];assert p.is_file() and p.stat().st_size==rec['bytes'] and sha(p)==rec['sha256'],rec['name']
    assert rec['owner_only'] and rec['restricted_parent_verified'] and rec['remote_readback_verified'] and rec['drive_id']
    return p

def checked_zip(p):
    z=zipfile.ZipFile(p);assert z.testzip() is None
    mf=next(n for n in ('checkpoint_manifest.json','checkpoint.private.json','manifest.json') if n in z.namelist())
    m=json.loads(z.read(mf));files=m.get('files',m.get('members'));assert files
    assert set(z.namelist())==set(files)|{mf}
    for name,r in files.items():
        v=z.read(name);assert len(v)==r['bytes'] and bytesha(v)==r['sha256'],(p,name)
    return z,m,files

def finalize(base,root,roster,index):
    assert sha(roster)==ROSTER
    result=audit(base,roster,neighbors=False)
    assert result['projections_verified']==24 and result['eom_partitions_verified']==144 and not result['missing_projection_indices']
    assert len(result['within_view_seed_stability'])==72
    entries=[];leaves=Counter(); expected=config_grid()
    assert len(index['checkpoints'])==25 and len({r['drive_id'] for r in index['checkpoints']})==25
    assert set(r['config_index'] for r in index['checkpoints'])==set(range(24))
    for cfg,ind in zip(expected,result['results']):
        i=cfg['index'];assert ind['config']==cfg and len(ind['partitions'])==6
        recs=[r for r in index['checkpoints'] if r['config_index']==i];assert len(recs)==(2 if i==0 else 1)
        path=base/'runs'/f"{cfg['view']}_d{cfg['n_components']}_k{cfg['n_neighbors']}_s{cfg['seed']}";seen=set();diagnostic=None;stored_leaf=None
        for rec in recs:
            p=checked_file(root,rec);z,m,files=checked_zip(p)
            with z:
                assert m['config']==cfg
                for name,r in files.items():
                    if name in RUN_FILES:
                        assert name not in seen and sha(path/name)==r['sha256'];seen.add(name)
                aname=next((x for x in files if x=='audit.private.json' or x.endswith('_AUDIT.json')),None)
                if aname:
                    a=json.loads(z.read(aname));assert a['roster_sha256']==ROSTER and a['projections_verified']==1 and a['eom_partitions_verified']==6
                    s=a['results'][0];assert s['config']==cfg and s['projection_sha256']==ind['projection_sha256'] and s['partitions']==ind['partitions']
                    diagnostic=s['full_candidate_knn_diagnostic'];assert diagnostic['query_count']==800 and diagnostic['candidate_count']==N and diagnostic['k']==15 and 0<=diagnostic['shared_neighbor_fraction']<=1
                    stored_leaf=a['conditional_leaf_verified'];assert stored_leaf==sum(p['leaf_triggered'] for p in ind['partitions'])
        assert seen==RUN_FILES and diagnostic is not None and stored_leaf is not None
        leaves[cfg['view']]+=stored_leaf
        entries.append({'config':cfg,'checkpoints':recs,'projection_sha256':ind['projection_sha256'],'eom_count':6,'conditional_leaf_count':stored_leaf,'full_candidate_knn_diagnostic':diagnostic,'partitions':ind['partitions']})
    assert sum(leaves.values())==result['conditional_leaf_verified']
    views={}
    for view in EXPECTED:
        r=index['diagnostics'][view];p=checked_file(root,r['sensitivity']);d=json.loads(p.read_text());assert d['view']==view and d['source_sha256']==EXPECTED[view] and d['roster_sha256']==ROSTER and d['n']==N and d['projections']==8 and d['eom_partitions']==48 and d['conditional_leaf_partitions']==leaves[view]
        assert len(d['single_factor_eom_pairs'])==144 and len(d['partition_diagnostics'])==48
        assert d['single_factor_pair_counts']=={'n_components':24,'n_neighbors':24,'seed':24,'min_samples':24,'min_cluster_size':48}
        for p2 in d['single_factor_eom_pairs']:
            assert p2['both_assigned']+p2['both_noise']+p2['assigned_a_only']+p2['assigned_b_only']==N
            assert sum(p2['a'][k]!=p2['b'][k] for k in p2['a'])==1 and p2['a'][p2['changed_factor']]!=p2['b'][p2['changed_factor']]
        p=checked_file(root,r['content']);z,m,files=checked_zip(p)
        with z:
            sname=next(n for n in files if n.endswith('_CONTENT_SAMPLE.json'));rname=next(n for n in files if n.endswith('_CONTENT_SPOTCHECK.json'))
            s=json.loads(z.read(sname));rev=json.loads(z.read(rname));assert s['view']==rev['view']==view and s['source_roster_match_all_rows'] and s['roster_sha256']==ROSTER and rev['sample_sha256']==bytesha(z.read(sname))
            assert s['fixed_diagnostic_threshold']=={'min_samples':10,'min_cluster_size':80}
            assert len(s['groups'])==len(rev['observations']) and s['sample_occurrences']==rev['sample_occurrences'] and s['unique_article_count']==rev['unique_article_count']
            assert set(g['config']['index'] for g in s['groups'])=={c['index'] for c in expected if c['view']==view}
            for i,(g,o) in enumerate(zip(s['groups'],rev['observations'])):
                assert o['group_index']==i and o['config_index']==g['config']['index'] and o['sample_row_indices']==g['sample_row_indices'] and o['method']==g['method'] and o['stratum']==g['stratum'] and o['cluster_label']==g['cluster_label']
            content={'groups':len(s['groups']),'sample_occurrences':s['sample_occurrences'],'unique_article_count':s['unique_article_count'],'title_only_count':rev['title_only_count'],'review_scope':rev['review_scope']}
        views[view]={'source_sha256':EXPECTED[view],'projections':8,'eom_partitions':48,'conditional_leaf_partitions':leaves[view],'within_view_single_factor_pairs':144,'content_spotcheck':content,'diagnostics':r}
    baseline=checked_file(root,index['baseline']);assert sha(baseline)==index['baseline']['sha256']
    return {'schema':'stage3-umap-hdbscan-full-grid-technical-acceptance/v1','status':'FULL_GRID_TECHNICALLY_VERIFIED__STAGE3_OPEN','n':N,'roster_sha256':ROSTER,'full_projections':24,'eom_partitions':144,'conditional_leaf_partitions':sum(leaves.values()),'views':views,'configurations':entries,'within_view_seed_stability':result['within_view_seed_stability'],'baseline_acceptance':index['baseline'],'checks':['full frozen roster and matrix SHA; every projection shape and finite','all EOM/leaf labels, strengths, coverage, counts and integer leaf trigger independently recomputed','all 25 fetched archive SHA, CRC, member SHA and run-file bytes','every stored full-candidate neighbor diagnostic matched to re-audited partition','all 3 within-view sensitivity and limited content review artifacts checked','baseline acceptance bytes unchanged'],'limitations':['No full dense-vs-implicit MST equivalence on full corpus; synthetic equivalence previously passed.','Content check is deterministic limited title/abstract-excerpt spot check, not complete thematic validation or independent QA.','No cross-view comparison, ranking, baseline replacement, PR merge, stage closure or Stage4 transition.']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--archive-dir',type=Path,required=True);p.add_argument('--roster',type=Path,required=True);p.add_argument('--index',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=finalize(a.base,a.archive_dir,a.roster,json.loads(a.index.read_text()));
    with a.out.open('x') as f:json.dump(r,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
    a.out.chmod(0o600);print(json.dumps({k:r[k] for k in ('status','full_projections','eom_partitions','conditional_leaf_partitions')}));print('sha256',sha(a.out))
if __name__=='__main__': main()

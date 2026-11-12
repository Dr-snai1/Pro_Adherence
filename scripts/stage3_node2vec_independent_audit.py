"""Independent read-only auditor for private full-CPU node2vec output.

No training, private identifiers or embedding values in its summary report.
Recounts original frozen graph independently from the production runner.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile
import numpy as np

EXPECTED_GRAPH='33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c'

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def audit(graph,asset):
    graph_sha=digest(graph)
    if graph_sha!=EXPECTED_GRAPH:raise ValueError('input graph sha mismatch')
    with zipfile.ZipFile(graph) as z:
        if z.testzip() is not None:raise ValueError('graph zip CRC invalid')
        mani=json.loads(z.read('node2vec_graph_manifest.private.json'))
        for name,spec in mani['outputs'].items():
            b=z.read(name)
            if hashlib.sha256(b).hexdigest()!=spec['sha256']:raise ValueError('source member SHA invalid')
        with gzip.open(z.open('node2vec_node_mapping.private.jsonl.gz'),'rt') as f:
            rows=[json.loads(line) for line in f]
        ids=[x['article_id'] for x in rows]
        n=len(ids)
        if n!=57204 or len(set(ids))!=n or any(x['node_index']!=i for i,x in enumerate(rows)):
            raise ValueError('source roster invalid')
        degrees=Counter()
        pairs=set()
        observations=0
        with gzip.open(z.open('node2vec_training_edges.private.jsonl.gz'),'rt') as f:
            for line in f:
                edge=json.loads(line)
                a=edge['source_article_id'];b=edge['target_article_id']
                if a==b or edge['weight']!=1:raise ValueError('invalid graph edge')
                p=tuple(sorted((a,b)))
                if p in pairs:raise ValueError('duplicate graph edge')
                pairs.add(p)
                degrees[a]+=1;degrees[b]+=1
                observations+=edge['observation_count']
        if len(pairs)!=328298 or len(degrees)!=43608 or n-len(degrees)!=13596:
            raise ValueError('source graph census unexpected')
        if observations!=406729:raise ValueError('source graph observation count unexpected')
    output_sha=digest(asset)
    with zipfile.ZipFile(asset) as z:
        if z.testzip() is not None:raise ValueError('output zip CRC failed')
        manifest=json.loads(z.read('manifest.private.json'))
        quality=json.loads(z.read('quality.private.json'))
        if manifest['graph_sha256']!=graph_sha:raise ValueError('graph lineage mismatch')
        if manifest['full_canonical_eligible_count']!=n or manifest['nonisolated_trained']!=43608 or manifest['isolates_null']!=13596:
            raise ValueError('manifest census mismatch')
        if manifest['backend_config']['negative']!=5 or manifest['backend_config']['sample']!=0.001:
            raise ValueError('owner-approved configuration mismatch')
        if manifest['backend_config']['seed']!=20261031 or manifest['backend_config']['p']!=1 or manifest['backend_config']['q']!=1:
            raise ValueError('walk config mismatch')
        if len(manifest['walk_stats'])<2 or any(v['walks']!=436080 or v['tokens']!=17443200 for v in manifest['walk_stats']):
            raise ValueError('full walk coverage missing')
        if len({v['sha256'] for v in manifest['walk_stats']})!=1:raise ValueError('walk replay not deterministic')
        if not manifest.get('model_identity_hash') or len(manifest['model_identity_hash'])!=64:
            raise ValueError('model identity absent')
        for name,spec in manifest['files'].items():
            b=z.read(name)
            if len(b)!=spec['size_bytes'] or hashlib.sha256(b).hexdigest()!=spec['sha256']:
                raise ValueError('output member digest mismatch: '+name)
        arrays={name:np.load(io.BytesIO(z.read(name)),allow_pickle=False) for name in ['raw.float32.npy','unit.float32.npy','raw_l2_norm.float64.npy','node_indices.int32.npy']}
        raw=arrays['raw.float32.npy'];unit=arrays['unit.float32.npy'];norm=arrays['raw_l2_norm.float64.npy'];indices=arrays['node_indices.int32.npy']
        if raw.shape!=(43608,128) or unit.shape!=(43608,128) or norm.shape!=(43608,) or indices.shape!=(43608,):
            raise ValueError('array shape mismatch')
        if raw.dtype!=np.float32 or unit.dtype!=np.float32 or norm.dtype!=np.float64 or indices.dtype!=np.int32:
            raise ValueError('incorrect vector dtype')
        if not (np.isfinite(raw).all() and np.isfinite(unit).all() and np.isfinite(norm).all()):
            raise ValueError('nonfinite numeric output')
        if (norm<=0).any() or not np.allclose(np.linalg.norm(raw.astype(np.float64),axis=1),norm,atol=1e-7,rtol=1e-7):
            raise ValueError('norm corruption')
        if not np.allclose(np.linalg.norm(unit.astype(np.float64),axis=1),1,atol=1e-5,rtol=0):
            raise ValueError('unit not unit')
        if not np.allclose(raw,unit*norm[:,None],rtol=3e-6,atol=3e-6):
            raise ValueError('vector reconstruction failed')
        expected_indices=[i for i,id in enumerate(ids) if id in degrees]
        if not np.array_equal(indices,np.asarray(expected_indices,dtype=np.int32)):
            raise ValueError('vector node indices mismatch independent graph')
        ready=missing=0
        with gzip.GzipFile(fileobj=io.BytesIO(z.read('article_status.private.jsonl.gz')),mode='rb') as f:
            for i,line in enumerate(f):
                row=json.loads(line)
                if i>=n or row['canonical_article_id']!=ids[i] or row['node_index']!=i:
                    raise ValueError('roster ID mismatch')
                if ids[i] in degrees:
                    if row['status']!='ready' or row['vector_row']!=ready:
                        raise ValueError('incorrect ready mapping')
                    ready+=1
                else:
                    if row['status']!='missing_structural' or row['vector_row'] is not None:
                        raise ValueError('isolates not null')
                    missing+=1
        if ready!=43608 or missing!=13596 or ready+missing!=n:
            raise ValueError('roster coverage incomplete')
    return {'schema':'pro-adherence-stage3-node2vec-independent-audit/v1',
            'result':'INDEPENDENT_GRAPH_RECOUNT_AND_NUMERIC_OUTPUT_PASS',
            'graph_sha256':graph_sha,'asset_sha256':output_sha,
            'asset_bytes':Path(asset).stat().st_size,'model_identity_hash':manifest['model_identity_hash'],
            'graph_edges':len(pairs),'eligible_observations':observations,
            'eligible_nodes':n,'trained_vectors':ready,'isolates_null':missing,'dimensions':128,
            'walks_per_pass':436080,'tokens_per_pass':17443200,
            'full_walk_passes_replayed_identically':len(manifest['walk_stats']),
            'raw_norm_unit_numerical_verification':True,
            'source_graph_roster_vs_output_index_independent_match':True,
            'no_private_identifiers_or_vectors_in_report':True}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graph',type=Path,required=True)
    p.add_argument('--asset',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise SystemExit('refuse overwrite')
    r=audit(a.graph,a.asset)
    a.out.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print('INDEPENDENT_FULL_NODE2VEC_AUDIT_PASS',json.dumps({'trained':r['trained_vectors'],'asset_sha256':r['asset_sha256']}))
if __name__=='__main__':main()

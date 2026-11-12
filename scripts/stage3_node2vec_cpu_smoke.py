"""Strictly bounded node2vec p=q=1 CPU technical smoke on an immutable PRIVATE graph.

No full node2vec training, no release, no private row identifiers in reports.
The test uses 1% of the accepted nominal walks on full-graph adjacency,
never an induced subgraph. Do NOT treat pilot vectors as production embeddings.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import time
import zipfile

import numpy as np
from gensim.models import Word2Vec

SCHEMA = 'pro-adherence-stage3-node2vec-bounded-cpu-smoke/v1'
GRAPH_SHA = '33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c'
N_NODES=57204
N_EDGES=328298
N_ISOLATES=13596
SEED=20261031
WALK_LENGTH=40
WALKS_PER_NODE=10
DIM=128
WINDOW=10
EPOCHS=1
# Approved by owner 2026-11-12 (not approval to run full training).
NEGATIVE=5
SAMPLE=0.001
# Existing skip-gram implementation semantics, now explicit.
SG=1
HS=0
MIN_COUNT=1
SORTED_VOCAB=1
WORKERS=1
MAX_START_NODES=436  # 436*10 = 4,360/436,080 nominal walks: 0.99977%


def file_sha(path: Path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for piece in iter(lambda:f.read(1024*1024),b''): h.update(piece)
    return h.hexdigest()


def secure_load(path: Path):
    assert file_sha(path)==GRAPH_SHA, 'frozen graph hash changed'
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        manifest=json.loads(z.read('node2vec_graph_manifest.private.json'))
        expected={
            'node2vec_node_mapping.private.jsonl.gz',
            'node2vec_training_edges.private.jsonl.gz',
            'directed_edges.private.jsonl.gz',
            'directed_citation_evidence.private.jsonl.gz',
        }
        assert set(manifest['outputs'])==expected
        for name,entry in manifest['outputs'].items():
            bb=z.read(name)
            assert hashlib.sha256(bb).hexdigest()==entry['sha256']
            assert len(bb)==entry['size_bytes']
        with gzip.open(z.open('node2vec_node_mapping.private.jsonl.gz'),'rt',encoding='utf-8') as f:
            rows=[json.loads(x) for x in f]
        assert len(rows)==N_NODES and all(r['node_index']==i for i,r in enumerate(rows))
        article_ids=[r['article_id'] for r in rows]
        assert len(set(article_ids))==N_NODES
        lookup={v:i for i,v in enumerate(article_ids)}
        degrees=np.zeros(N_NODES,dtype=np.int32)
        indices=[]
        with gzip.open(z.open('node2vec_training_edges.private.jsonl.gz'),'rt',encoding='utf-8') as f:
            for raw in f:
                e=json.loads(raw);a=lookup[e['source_article_id']];b=lookup[e['target_article_id']]
                assert a!=b and e['weight']==1 and e['observation_count']>=1
                degrees[a]+=1;degrees[b]+=1;indices.append((a,b))
        assert len(indices)==N_EDGES
        assert int(np.count_nonzero(degrees==0))==N_ISOLATES
        offsets=np.zeros(N_NODES+1,dtype=np.int64)
        np.cumsum(degrees,out=offsets[1:])
        adj=np.empty(int(offsets[-1]),dtype=np.int32)
        cursors=offsets[:-1].copy()
        for a,b in indices:
            adj[cursors[a]]=b;cursors[a]+=1
            adj[cursors[b]]=a;cursors[b]+=1
        for i in range(N_NODES):
            adj[offsets[i]:offsets[i+1]].sort()
        assert all(int(degrees[i])==len(set(map(int,adj[offsets[i]:offsets[i+1]]))) for i in range(N_NODES))
        return degrees,offsets,adj


def choose_starts(degrees):
    # Technical stress coverage of low/medium/high/hub degrees, not a scientific sample.
    buckets=[np.flatnonzero((degrees>=1)&(degrees<=3)),
             np.flatnonzero((degrees>=4)&(degrees<=9)),
             np.flatnonzero((degrees>=10)&(degrees<=33)),
             np.flatnonzero(degrees>=34)]
    assert all(len(x)>109 for x in buckets),[len(x) for x in buckets]
    rng=np.random.default_rng(SEED)
    starts=np.concatenate([rng.choice(b,size=MAX_START_NODES//4,replace=False) for b in buckets])
    assert len(starts)==MAX_START_NODES
    assert len(set(map(int,starts)))==len(starts)
    return starts, list(map(len,buckets))


def walk_generator(starts,offsets,adj,seed):
    assert WALK_LENGTH==40 and WALKS_PER_NODE==10
    rng=np.random.default_rng(seed)
    starts=np.asarray(starts,dtype=np.int32)
    for _ in range(WALKS_PER_NODE):
        order=rng.permutation(starts)
        for start in order:
            cur=int(start); walk=[str(cur)]
            for _ in range(WALK_LENGTH-1):
                lo=int(offsets[cur]);hi=int(offsets[cur+1])
                assert hi>lo
                cur=int(adj[lo+int(rng.integers(hi-lo))])  # node2vec alpha=1 for p=q=1; uniform binary edges
                walk.append(str(cur))
            yield walk


class RepeatableWalkCorpus:
    """Re-iterable deterministic walk stream for Gensim's vocabulary/train passes.

    Uses the full supplied adjacency, but materializes no list of walks. Only
    synthetic/bounded tests are authorized; instantiation does NOT train.
    """
    def __init__(self, starts, offsets, adj, seed=SEED):
        self.starts=np.asarray(starts,dtype=np.int32).copy()
        self.offsets=offsets
        self.adj=adj
        self.seed=seed

    def __iter__(self):
        return walk_generator(self.starts,self.offsets,self.adj,self.seed)


def walk_digest(walks):
    h=hashlib.sha256()
    for walk in walks:
        h.update(','.join(walk).encode('ascii')+b'\n')
    return h.hexdigest()


def train(walks, seed):
    # P1 only: backend negative/sample approved 2026-11-12, NOT full training.
    # Stable SHA-derived initialization avoids Python process salted hash behavior.
    stable_hash=lambda s: int.from_bytes(hashlib.sha256(s.encode('utf-8')).digest()[:8], 'little')
    return Word2Vec(sentences=walks,vector_size=DIM,window=WINDOW,min_count=MIN_COUNT,
        sg=SG,hs=HS,negative=NEGATIVE,sample=SAMPLE,workers=WORKERS,
        epochs=EPOCHS,seed=seed,hashfxn=stable_hash,sorted_vocab=SORTED_VOCAB)


def vectors_digest(model):
    vocab_sorted=sorted(model.wv.index_to_key,key=lambda s:int(s))
    h=hashlib.sha256()
    for key in vocab_sorted:
        h.update(key.encode('ascii')+b'\0')
        h.update(np.ascontiguousarray(model.wv[key],dtype=np.float32).tobytes())
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--graph',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    assert not a.out.exists(), 'refuse overwrite'
    started=time.monotonic()
    degree,offsets,adj=secure_load(a.graph)
    starts,bucket_pop=choose_starts(degree)
    walks=list(walk_generator(starts,offsets,adj,SEED))
    assert len(walks)==MAX_START_NODES*WALKS_PER_NODE==4360
    assert all(len(w)==WALK_LENGTH for w in walks)
    w_hash=walk_digest(walks)
    assert w_hash==walk_digest(walk_generator(starts,offsets,adj,SEED)), 'same-seed walks nonreproducible'
    assert w_hash!=walk_digest(walk_generator(starts,offsets,adj,SEED+1)), 'seed variation not observed'
    print('GRAPH_AND_WALKS_PASS',len(walks),WALK_LENGTH,w_hash,flush=True)
    t=time.monotonic()
    model=train(walks,SEED)
    train_sec=time.monotonic()-t
    h1=vectors_digest(model)
    t=time.monotonic()
    model2=train(walks,SEED)
    repeat_sec=time.monotonic()-t
    h2=vectors_digest(model2)
    assert h1==h2,'same seed training not bitwise reproducible'
    vectors=model.wv.vectors
    assert vectors.dtype==np.float32 and vectors.shape[1]==DIM
    assert np.isfinite(vectors).all()
    norm=np.linalg.norm(vectors.astype('float64'),axis=1)
    assert np.all(norm>0)
    unit=(vectors/norm[:,None]).astype(np.float32)
    assert np.allclose(np.linalg.norm(unit.astype('float64'),axis=1),1,atol=1e-5)
    m_other=train(walks,SEED+1)
    other_hash=vectors_digest(m_other)
    assert other_hash!=h1, 'seed sensitivity smoke not observed'
    assert set(model.wv.index_to_key).issubset({str(i) for i in range(N_NODES) if degree[i]>0})
    assert set(model.wv.index_to_key).isdisjoint({str(i) for i in range(N_NODES) if degree[i]==0})
    report={
      'schema':SCHEMA,'result':'BOUNDED_PILOT_PASS_NOT_FULL_TRAINING',
      'graph_sha256':GRAPH_SHA,'approved_scientific_method':{'p':1,'q':1,'dimensions':DIM,'walk_length':WALK_LENGTH,'walks_per_node':WALKS_PER_NODE,'window':WINDOW,'epochs':EPOCHS,'seed':SEED,'graph':'full frozen undirected binary graph'},
      'scope':{'pilot_starts':MAX_START_NODES,'start_selection':'degree-stratified technical stress sample; not a scientific sample',
         'degree_bucket_population':bucket_pop,'pilot_walks':len(walks),'nominal_full_walks':436080,
         'pilot_walk_fraction':len(walks)/436080,'pilot_tokens':len(walks)*WALK_LENGTH,'nominal_full_tokens':17443200,
         'full_graph_nodes':N_NODES,'full_graph_undirected_edges':N_EDGES,'isolates':N_ISOLATES,
         'word2vec_pilot_vocabulary':len(model.wv),'full_embeddings_produced':False},
      'runtime':{'python':os.sys.version.split()[0],'numpy':np.__version__,'gensim':__import__('gensim').__version__,
                 'workers':1,'gensim_sg':1,'negative':model.negative,'sample':model.sample,'min_count':1,
                 'training_seconds':round(train_sec,3),'identical_repeat_seconds':round(repeat_sec,3),
                 'total_seconds':round(time.monotonic()-started,3),'ru_maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
      'independent_checks':{'archive_sha_crc_manifest_all_members':True,'full_adjacency_degree_isolates':True,
         'walks_same_seed_exact_sha':True,'walks_different_seed_changed':True,
         'gensim_same_seed_vector_sha_identical':True,'gensim_changed_seed_vector_sha_different':True,
         'finite_float32_128d_vectors_and_l2_norms':True,'isolates_never_vocabulary':True},
      'walk_sha256':w_hash,'pilot_vectors_sha256_same_seed':h1,'pilot_vectors_sha256_alternative_seed':other_hash,
      'saved_private_canonical_ids_or_vectors':False,'publication_authorized':False,
      'next':'separate owner-scoped full training after measured RAM and full dependency lock plus seed reproducibility; this P1 does not replace complete node2vec embedding asset'
    }
    a.out.write_text(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('NODE2VEC_BOUNDED_CPU_SMOKE_PASS',json.dumps({'pilot_walks':len(walks),'vocab':len(model.wv),'seconds':report['runtime']['total_seconds'],'rss_kib':report['runtime']['ru_maxrss_kib']}),flush=True)

if __name__=='__main__':main()

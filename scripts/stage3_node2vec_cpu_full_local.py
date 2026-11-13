"""Owner-scoped Stage 3 node2vec full CPU training on frozen PRIVATE graph.

Never upload research inputs, article IDs, graph rows or vectors to GitHub.
This executable is authorized ONLY for owner-scoped local, no-cost CPU run,
with full immutable SHA/CRC checks and owner-only durable Drive storage.
"""
from __future__ import annotations
if not __debug__:
    raise SystemExit('Python -O forbidden: integrity gates must run')

import argparse
import gzip
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import threading
import time
import zipfile

import numpy as np
from gensim.models import Word2Vec

GRAPH_SHA='33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c'
EXPECTED_MEMBERS={
    'node2vec_node_mapping.private.jsonl.gz',
    'node2vec_training_edges.private.jsonl.gz',
    'directed_edges.private.jsonl.gz',
    'directed_citation_evidence.private.jsonl.gz',
}
VERSIONS={'gensim':'4.4.0','numpy':'2.3.5','scipy':'1.17.0','smart_open':'7.6.1','wrapt':'2.2.1'}
SEED=20261031
N_NODES=57204
N_EDGES=328298
N_ISOLATES=13596
N_ACTIVE=N_NODES-N_ISOLATES
WALKS_PER_NODE=10
WALK_LENGTH=40
DIM=128
WINDOW=10
EPOCHS=1
NEGATIVE=5
SAMPLE=0.001


def fail(reason):
    raise RuntimeError(reason)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1<<20),b''):
            h.update(block)
    return h.hexdigest()


def announce(event,**values):
    print(json.dumps({'event':event,**values},sort_keys=True),flush=True)


def ensure_runtime():
    if sys.version_info[:2]!=(3,13) or platform.machine().lower() not in ('x86_64','amd64'):
        fail('approved wheel ABI needs CPython 3.13 x86_64')
    observed={x:importlib.metadata.version(x) for x in VERSIONS}
    if observed!=VERSIONS:
        fail('CPU version pin mismatch: '+repr(observed))
    if shutil.disk_usage('/mnt/data').free < 500_000_000:
        fail('free disk space below 500MB')
    cap_path=Path('/sys/fs/cgroup/memory.max')
    current_path=Path('/sys/fs/cgroup/memory.current')
    mem_cap=None
    if cap_path.exists() and cap_path.read_text().strip()!='max':
        mem_cap=int(cap_path.read_text().strip())
        used=int(current_path.read_text().strip())
        if mem_cap-used < 800_000_000:
            fail('insufficient cgroup memory headroom before run')
    announce('RUNTIME_OK',python=sys.version.split()[0],packages=observed,mem_cap_bytes=mem_cap)
    return observed,mem_cap


def load_graph(path):
    if sha_file(path)!=GRAPH_SHA:
        fail('private graph zip sha mismatch')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            fail('graph zip CRC failure')
        manifest=json.loads(z.read('node2vec_graph_manifest.private.json'))
        if set(manifest['outputs'])!=EXPECTED_MEMBERS:
            fail('graph member inventory mismatch')
        for name,entry in manifest['outputs'].items():
            bb=z.read(name)
            if sha_bytes(bb)!=entry['sha256'] or len(bb)!=entry['size_bytes']:
                fail('graph member bytes mismatch: '+name)
        with gzip.open(z.open('node2vec_node_mapping.private.jsonl.gz'),'rt',encoding='utf-8') as f:
            roster=[json.loads(line) for line in f]
        if len(roster)!=N_NODES or any(x['node_index']!=i for i,x in enumerate(roster)):
            fail('frozen node mapping count/order mismatch')
        article_ids=[x['article_id'] for x in roster]
        if len(set(article_ids))!=N_NODES:
            fail('duplicate canonical article ID in graph mapping')
        idx={id:i for i,id in enumerate(article_ids)}
        deg=np.zeros(N_NODES,dtype=np.int32)
        edge_pairs=[]
        seen=set()
        with gzip.open(z.open('node2vec_training_edges.private.jsonl.gz'),'rt',encoding='utf-8') as f:
            for line in f:
                obj=json.loads(line)
                a=idx[obj['source_article_id']];b=idx[obj['target_article_id']]
                if a==b or obj['weight']!=1 or obj['observation_count']<1:
                    fail('invalid frozen edge')
                p=(min(a,b),max(a,b))
                if p in seen:
                    fail('duplicate frozen unordered edge')
                seen.add(p)
                edge_pairs.append((a,b))
                deg[a]+=1;deg[b]+=1
        if len(edge_pairs)!=N_EDGES or np.count_nonzero(deg==0)!=N_ISOLATES:
            fail('graph edge/isolate counts mismatch')
        offsets=np.zeros(N_NODES+1,dtype=np.int64)
        np.cumsum(deg,out=offsets[1:])
        adj=np.empty(int(offsets[-1]),dtype=np.int32)
        cur=offsets[:-1].copy()
        for a,b in edge_pairs:
            adj[cur[a]]=b;cur[a]+=1
            adj[cur[b]]=a;cur[b]+=1
        if not np.array_equal(cur,offsets[1:]):
            fail('CSR offset fill mismatch')
        for i in range(N_NODES):
            adj[offsets[i]:offsets[i+1]].sort()
        active=np.flatnonzero(deg>0).astype('int32')
        if len(active)!=N_ACTIVE:
            fail('nonisolated count mismatch')
        announce('GRAPH_VERIFIED',nodes=N_NODES,edges=N_EDGES,isolates=N_ISOLATES,active=N_ACTIVE)
        return article_ids,deg,offsets,adj,active,manifest


class ReiterableFullWalks:
    """Exactly ten fixed-seed randomized starts per nonisolate on FULL adjacency.

    Gensim builds vocabulary and trains using separate __iter__ passes.
    Each pass is independently regenerated and has a full walk SHA and count.
    """
    def __init__(self,active,offsets,adj):
        self.active=active
        self.offsets=offsets
        self.adj=adj
        self.ascii_nodes=[str(i) for i in range(N_NODES)]
        self.stats=[]

    def __iter__(self):
        rng=np.random.default_rng(SEED)
        h=hashlib.sha256()
        count=0
        for _ in range(WALKS_PER_NODE):
            for seed_node in rng.permutation(self.active):
                cur=int(seed_node)
                walk=[self.ascii_nodes[cur]]
                for _ in range(WALK_LENGTH-1):
                    lo=int(self.offsets[cur]);hi=int(self.offsets[cur+1])
                    if hi<=lo:
                        fail('walk reached isolate')
                    cur=int(self.adj[lo+int(rng.integers(hi-lo))])
                    walk.append(self.ascii_nodes[cur])
                count+=1
                h.update(','.join(walk).encode('ascii')+b'\n')
                yield walk
        info={'pass':len(self.stats)+1,'walks':count,'tokens':count*WALK_LENGTH,'sha256':h.hexdigest()}
        self.stats.append(info)
        announce('WALK_PASS_COMPLETE',**info)


def fixed_hash(word):
    return int.from_bytes(hashlib.sha256(word.encode('utf-8')).digest()[:8],'little')


def safe_stop_watcher(mem_cap,stop_event,output_dir):
    if mem_cap is None:
        return
    current=Path('/sys/fs/cgroup/memory.current')
    threshold=mem_cap-max(512*1024*1024,mem_cap//10)
    while not stop_event.wait(0.75):
        try:
            if int(current.read_text().strip())>threshold:
                (output_dir/'STOP_MEMORY_LIMIT.txt').write_text('cgroup memory safety threshold reached; no accepted asset\n')
                os._exit(73)
        except OSError:
            pass


def npy_bytes(array):
    out=io.BytesIO()
    np.save(out,array,allow_pickle=False)
    return out.getvalue()


def stable_zip_write(z,name,data):
    info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
    info.compress_type=zipfile.ZIP_STORED
    info.external_attr=0o600<<16
    z.writestr(info,data)


def make_outputs(outzip,article_ids,deg,active,model,walk_stats,graph_manifest,versions,fit_seconds):
    expected={str(int(i)) for i in active}
    actual=set(model.wv.index_to_key)
    if actual!=expected:
        fail('TRAINED VOCABULARY IS NOT FULL 43608 NONISOLATED NODES')
    if model.wv.vector_size!=DIM or model.negative!=NEGATIVE or model.sample!=SAMPLE or model.sg!=1 or model.hs!=0:
        fail('trained model backend diverged from accepted config')
    raw=np.ascontiguousarray(np.stack([model.wv[str(int(i))] for i in active]),dtype=np.float32)
    norm=np.linalg.norm(raw.astype(np.float64),axis=1).astype(np.float64)
    if raw.shape!=(N_ACTIVE,DIM) or not np.isfinite(raw).all() or not np.isfinite(norm).all() or np.any(norm<=0):
        fail('infinite, missing or zero raw norm')
    unit=np.ascontiguousarray((raw/norm[:,None]).astype(np.float32))
    if not np.allclose(np.linalg.norm(unit.astype(np.float64),axis=1),1,atol=1e-5,rtol=0):
        fail('unit norm not approximately 1')
    if not np.allclose(raw,unit*norm[:,None],atol=3e-6,rtol=3e-6):
        fail('raw norm unit reconstruction invalid')
    if len(walk_stats)<2 or len({p['sha256'] for p in walk_stats})!=1 or any(p['walks']!=N_ACTIVE*WALKS_PER_NODE for p in walk_stats):
        fail('full walk passes mismatch: incomplete or not deterministic')
    vindex={int(i):j for j,i in enumerate(active)}
    status_io=io.BytesIO()
    with gzip.GzipFile(fileobj=status_io,mode='wb',filename='',mtime=0,compresslevel=6) as g:
        for i,article_id in enumerate(article_ids):
            ok=bool(deg[i]>0)
            row={'canonical_article_id':article_id,'node_index':i,
                 'status':'ready' if ok else 'missing_structural',
                 'vector_row':vindex[i] if ok else None}
            g.write((json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8'))
    arrays={
        'node_indices.int32.npy':npy_bytes(active),
        'raw.float32.npy':npy_bytes(raw),
        'raw_l2_norm.float64.npy':npy_bytes(norm),
        'unit.float32.npy':npy_bytes(unit),
        'article_status.private.jsonl.gz':status_io.getvalue(),
    }
    config={'p':1,'q':1,'dimensions':DIM,'walk_length':WALK_LENGTH,
            'walks_per_node':WALKS_PER_NODE,'window':WINDOW,'epochs':EPOCHS,
            'seed':SEED,'negative':NEGATIVE,'sample':SAMPLE,
            'sg':1,'hs':0,'workers':1,'min_count':1,'sorted_vocab':1,
            'gensim_defaults':{'shrink_windows':model.shrink_windows,
                               'ns_exponent':model.ns_exponent,
                               'alpha':model.alpha,'min_alpha':model.min_alpha},
            'token_hash':'sha256(token UTF8) first 8 bytes little endian',
            'source_graph':'frozen undirected binary exact DOI eligible graph'}
    model_material={'graph_sha256':GRAPH_SHA,'config':config,'versions':versions,
                    'code_sha256':sha_file(Path(__file__)),
                    'full_raw_vectors_sha256':sha_bytes(arrays['raw.float32.npy'])}
    model_id=sha_bytes(json.dumps(model_material,sort_keys=True,separators=(',',':')).encode('utf-8'))
    quality={
        'full_graph_nodes':N_NODES,'eligible_nonisolated_ready':N_ACTIVE,
        'missing_structural_null':N_ISOLATES,'vector_dim':DIM,
        'raw_finite_all':True,'norm_positive_all':True,'unit_norm_all':True,
        'raw_reconstruction_all':True,'trained_vocabulary_exact_all_nonisolates':True,
        'source_graph_full_crc_and_member_shas_pass':True,
        'walk_passes':walk_stats,'full_trained_embeddings_produced':True,
        'owner_scoped_local_cpu_only':True,'paid_compute':False,
        'public_release':False,'stage_transition':False,
    }
    manifest={'schema':'pro-adherence-stage3-node2vec-full-cpu-private/v1',
              'status':'FULL_TRAINED_SELF_AUDITED_AWAITING_PRIVATE_REMOTE_READBACK',
              'model_ref_id':'node2vec:'+model_id,
              'model_identity_hash':model_id,
              'computation_signature':model_id,
              'graph_sha256':GRAPH_SHA,
              'graph_input_manifest_sha256':sha_bytes(json.dumps(graph_manifest,sort_keys=True).encode('utf-8')),
              'full_canonical_eligible_count':N_NODES,
              'nonisolated_trained':N_ACTIVE,'isolates_null':N_ISOLATES,
              'runtime_versions':versions,'python':sys.version.split()[0],
              'code_sha256':sha_file(Path(__file__)),
              'backend_config':config,
              'fit_elapsed_seconds':round(fit_seconds,3),
              'walk_stats':walk_stats,
              'files':{name:{'sha256':sha_bytes(data),'size_bytes':len(data)} for name,data in arrays.items()},
              'private':True,'owner_full_cpu_authorization_date':'2026-11-12',
              'publication_authorized':False,'pr_merge_authorized':False,'stage_gate_authorized':False}
    bmanifest=(json.dumps(manifest,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    bquality=(json.dumps(quality,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    temp=Path(str(outzip)+'.incomplete')
    if temp.exists() or outzip.exists():
        fail('refuse overwrite of previous asset or incomplete artifact')
    with zipfile.ZipFile(temp,'w') as z:
        for name,data in arrays.items():
            stable_zip_write(z,name,data)
        stable_zip_write(z,'manifest.private.json',bmanifest)
        stable_zip_write(z,'quality.private.json',bquality)
    with zipfile.ZipFile(temp) as z:
        if z.testzip() is not None:
            fail('output ZIP CRC failure')
        for name,spec in manifest['files'].items():
            bb=z.read(name)
            if len(bb)!=spec['size_bytes'] or sha_bytes(bb)!=spec['sha256']:
                fail('output ZIP readback member SHA failure')
        with gzip.GzipFile(fileobj=io.BytesIO(z.read('article_status.private.jsonl.gz')),mode='rb') as g:
            ready=missing=0
            for node_idx,line in enumerate(g):
                row=json.loads(line)
                if row['node_index']!=node_idx or row['canonical_article_id']!=article_ids[node_idx]:
                    fail('re-read roster identity/order mismatch')
                if row['status']=='ready':
                    ready+=1
                    if row['vector_row']!=vindex[node_idx]:
                        fail('re-read row mapping mismatch')
                elif row['status']=='missing_structural':
                    missing+=1
                    if row['vector_row'] is not None:
                        fail('isolate received vector row')
                else:
                    fail('unknown vector status')
            if ready!=N_ACTIVE or missing!=N_ISOLATES or ready+missing!=N_NODES:
                fail('output roster coverage mismatch')
        for name,expected_shape in [('raw.float32.npy',(N_ACTIVE,DIM)),
                                     ('unit.float32.npy',(N_ACTIVE,DIM)),
                                     ('raw_l2_norm.float64.npy',(N_ACTIVE,)),
                                     ('node_indices.int32.npy',(N_ACTIVE,))]:
            arr=np.load(io.BytesIO(z.read(name)),allow_pickle=False)
            if arr.shape!=expected_shape:
                fail('output array shape mismatch: '+name)
    temp.replace(outzip)
    announce('ASSET_LOCAL_QA_PASS',output_name=outzip.name,
             bytes=outzip.stat().st_size,sha256=sha_file(outzip),
             model_identity_hash=model_id,ready=N_ACTIVE,missing=N_ISOLATES)
    return manifest,quality


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--graph',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if not args.graph.is_file() or args.out.exists():
        fail('missing graph or existing output file')
    versions,mem_cap=ensure_runtime()
    article_ids,deg,offsets,adj,active,graph_manifest=load_graph(args.graph)
    stream=ReiterableFullWalks(active,offsets,adj)
    event=threading.Event()
    guard=threading.Thread(target=safe_stop_watcher,args=(mem_cap,event,args.out.parent),daemon=True)
    guard.start()
    try:
        announce('FULL_TRAINING_START',walks_expected=N_ACTIVE*WALKS_PER_NODE,
                 tokens_expected=N_ACTIVE*WALKS_PER_NODE*WALK_LENGTH,
                 dimensions=DIM,workers=1,negative=NEGATIVE,sample=SAMPLE)
        start=time.monotonic()
        model=Word2Vec(sentences=stream,vector_size=DIM,window=WINDOW,
                       min_count=1,sg=1,hs=0,negative=NEGATIVE,sample=SAMPLE,
                       workers=1,epochs=EPOCHS,seed=SEED,hashfxn=fixed_hash,sorted_vocab=1)
        fit_seconds=time.monotonic()-start
        announce('FULL_TRAINING_FIT_COMPLETE',seconds=round(fit_seconds,3),
                 vocabulary=len(model.wv),num_walk_passes=len(stream.stats))
        make_outputs(args.out,article_ids,deg,active,model,stream.stats,graph_manifest,versions,fit_seconds)
    finally:
        event.set()
        guard.join(timeout=2)


if __name__=='__main__':main()

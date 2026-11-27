"""Restore full classic graph projections from frozen directed exact DOI evidence.
Verify exact PAC1 byte digest, preserving edge weights and eligible node mapping.
No network calls, no private inputs in source.
"""
import sys, json, zipfile, gzip, hashlib, struct
from pathlib import Path
import numpy as np
from scipy.sparse import csr_matrix, triu
from numba import njit
N=57204
FROZEN_SHA='33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c'
EXPECTED={'direct':(328298,328298,43608,None), 'cocitation':(2055149,2891776,31746,'6fb952d2c3f5e3e955cec517902b777b45ae185c2d48ef312ac22f8f280c3fec'), 'coupling':(15871086,18490159,32635,'bf7502ac23eaed295025e59155c2e6ea2e96df09542239051e0eddd88f548f46')}
def sha(path):
    with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
@njit
def pack_chunk(u,v,w,prev,n):
    buf=np.empty(10*len(u),np.uint8);j=0
    for i in range(len(u)):
        key=np.int64(u[i])*n+v[i];d=key-prev;prev=key
        assert d>0 and w[i]>0
        for val in (d,np.int64(w[i])):
            while val>=128:
                buf[j]=np.uint8((val&127)|128);j+=1;val>>=7
            buf[j]=np.uint8(val);j+=1
    return buf[:j],prev

def source(path):
    assert sha(path)==FROZEN_SHA
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        m=json.loads(z.read('node2vec_graph_manifest.private.json'))
        for k,r in m['outputs'].items():
            assert hashlib.sha256(z.read(k)).hexdigest()==r['sha256']
        def rows(name):
            with gzip.GzipFile(fileobj=z.open(name)) as f:
                for line in f: yield json.loads(line)
        mapping=list(rows('node2vec_node_mapping.private.jsonl.gz'))
        assert len(mapping)==N and all(r['node_index']==i for i,r in enumerate(mapping)); ids=[r['article_id'] for r in mapping];assert len(set(ids))==N
        idx={a:i for i,a in enumerate(ids)}
        pairs=[]
        for r in rows('directed_edges.private.jsonl.gz'):
            u=idx.get(r['source_article_id']);v=idx.get(r['target_article_id'])
            if u is not None and v is not None and u!=v:pairs.append((u,v))
        uv=np.array(pairs,dtype=np.int32);assert len(uv)==328307 and len(np.unique(uv[:,0].astype(np.int64)*N+uv[:,1]))==len(uv)
        A=csr_matrix((np.ones(len(uv),np.int32),(uv[:,0],uv[:,1])),shape=(N,N));A.sort_indices()
        train=[]
        for r in rows('node2vec_training_edges.private.jsonl.gz'):
            u=idx[r['source_article_id']];v=idx[r['target_article_id']];assert r['weight']==1 and u!=v;train.append(min(u,v)*N+max(u,v))
        assert len(train)==328298 and len(set(train))==328298
        assert np.array_equal(np.sort(np.array(train,np.int64)),np.unique(np.minimum(uv[:,0],uv[:,1]).astype(np.int64)*N+np.maximum(uv[:,0],uv[:,1])))
    return ids,A

def prepare(path,out):
    out.mkdir(parents=True,exist_ok=True);ids,A=source(path);results={}
    for name in EXPECTED:
        if name=='direct': B=triu(A.maximum(A.T),k=1,format='csr')
        elif name=='cocitation': B=triu(A.T@A,k=1,format='csr')
        else:B=triu(A@A.T,k=1,format='csr')
        B.sort_indices();u=np.repeat(np.arange(N,dtype=np.int32),np.diff(B.indptr));v=B.indices;w=B.data;assert np.all(u<v) and np.all(w>0)
        edge_count,weight_sum,active_count,expected_sha=EXPECTED[name]
        active=np.unique(np.concatenate((u,v)));assert len(u)==edge_count and int(w.sum(dtype=np.int64))==weight_sum and len(active)==active_count
        h=hashlib.sha256(struct.pack('<4sIII',b'PAC1',N,edge_count,weight_sum));prev=-1
        with (out/f'{name}.ncol').open('w') as f:
            for i in range(0,len(u),200000):
                s=slice(i,i+200000);packed,prev=pack_chunk(u[s],v[s],w[s],prev,N);h.update(packed.tobytes());np.savetxt(f,np.column_stack((u[s],v[s],w[s])),fmt='%d')
        if expected_sha:assert h.hexdigest()==expected_sha,(name,h.hexdigest())
        np.savez(out/f'{name}.npz',u=u,v=v,w=w,active=active)
        results[name]={'edges':edge_count,'total_weight':weight_sum,'active':active_count,'missing_structural':N-active_count,'pac1_sha256':h.hexdigest(),'original_pac1_match':expected_sha is not None,'ncol_sha256':sha(out/f'{name}.ncol'),'npz_sha256':sha(out/f'{name}.npz')}
        print(name,results[name],flush=True);del B,u,v,w,active
    (out/'mapping.json').write_text(json.dumps(ids));(out/'graph_preflight.json').write_text(json.dumps({'schema':'stage3-leiden-graph-preflight/v1','source_sha256':sha(path),'mapping_sha256':sha(out/'mapping.json'),'graphs':results},indent=2));
if __name__=='__main__':prepare(Path(sys.argv[1]),Path(sys.argv[2]))

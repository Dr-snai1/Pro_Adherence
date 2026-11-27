"""Full graph Leiden; explicit modularity resolution; independent edge-array verification.
Run after stage3_leiden_graphs.py. No external calls or private source data in code.
"""
import sys, json, gzip, hashlib, random, time, os
from pathlib import Path
from collections import Counter
import numpy as np
from numba import njit
import igraph as ig
from sklearn.metrics import adjusted_rand_score
from stage3_leiden_graphs import sha, N, EXPECTED
CONFIGS=[(.75,20261031),(1.,20261031),(1.25,20261031),(1.,20261032)]
@njit
def root(p,i):
    while p[i]!=i:
        p[i]=p[p[i]];i=p[i]
    return i
@njit
def audit_edges(u,v,w,labels,n,k):
    deg=np.zeros(k,np.float64);internal=np.zeros(k,np.float64);p=np.arange(n,dtype=np.int32)
    for i in range(len(u)):
        a=u[i];b=v[i];ca=labels[a];cb=labels[b];ww=w[i]
        assert ca>=0 and cb>=0
        deg[ca]+=ww;deg[cb]+=ww
        if ca==cb:
            internal[ca]+=ww
            ra=root(p,a);rb=root(p,b)
            if ra!=rb:p[rb]=ra
    reps=np.full(k,-1,np.int32);bad=np.zeros(k,np.uint8)
    for i in range(n):
        c=labels[i]
        if c>=0:
            r=root(p,i)
            if reps[c]==-1:reps[c]=r
            elif reps[c]!=r:bad[c]=1
    return deg,internal,bad

def run(directory,name):
    pre=json.loads((directory/'graph_preflight.json').read_text());m=pre['graphs'][name];assert sha(directory/'mapping.json')==pre['mapping_sha256'];ids=json.loads((directory/'mapping.json').read_text());assert len(ids)==N and len(set(ids))==N
    assert sha(directory/f'{name}.npz')==m['npz_sha256'] and sha(directory/f'{name}.ncol')==m['ncol_sha256'];assert ig.__version__=='0.11.9'
    with np.load(directory/f'{name}.npz',allow_pickle=False) as z:u,v,w,active=(z[k] for k in ('u','v','w','active'))
    assert (len(u),int(w.sum(dtype=np.int64)),len(active))==EXPECTED[name][:3];t=time.monotonic();g=ig.Graph.Read_Ncol(str(directory/f'{name}.ncol'),names=True,weights=True,directed=False);node=np.asarray(g.vs['name'],dtype=np.int32);assert g.ecount()==len(u) and g.vcount()==len(active) and np.array_equal(np.sort(node),active)
    deg=np.bincount(u,weights=w,minlength=N)+np.bincount(v,weights=w,minlength=N);assert np.array_equal(np.asarray(g.strength(weights='weight')),deg[node]);assert g.is_simple()
    reverse=np.full(N,-1,np.int32);reverse[node]=np.arange(len(node));rng=np.random.default_rng(20261127)
    for i in rng.choice(len(u),min(512,len(u)),replace=False):
        eid=g.get_eid(int(reverse[u[i]]),int(reverse[v[i]]));assert g.es[eid]['weight']==w[i]
    print(name,'graph loaded and degree/weight checks PASS',round(time.monotonic()-t,2),flush=True)
    results=[];labels=[]
    for gamma,seed in CONFIGS:
        t=time.monotonic();ig.set_random_number_generator(random.Random(seed));p=g.community_leiden(objective_function='modularity',weights='weight',resolution=gamma,beta=.01,n_iterations=-1);a=np.asarray(p.membership,dtype=np.int32);assert a.min()==0 and a.max()+1==len(p);y=np.full(N,-1,np.int32);y[node]=a;k=len(p)
        gd,internal,bad=audit_edges(u,v,w,y,N,k);assert not bad.any() and gd.sum()==2*m['total_weight'];q=float(np.sum(internal/m['total_weight']-gamma*(gd/(2*m['total_weight']))**2));q2=g.modularity(a.tolist(),weights='weight',resolution=gamma,directed=False);assert abs(q-q2)<1e-10,(q,q2)
        sizes=np.bincount(a);assert len(sizes)==k and sizes.min()>0 and sizes.sum()==len(active) and np.array_equal(np.flatnonzero(y>=0),active)
        # Canonicalize display ids by descending size then smallest frozen node index.
        first=np.full(k,N,np.int32);np.minimum.at(first,a,node);order=np.lexsort((first,-sizes));ren=np.empty(k,np.int32);ren[order]=np.arange(k);y[active]=ren[y[active]]
        rec={'resolution':gamma,'seed':seed,'n_iterations':-1,'clusters':k,'active':len(active),'structural_missing':N-len(active),'modularity':q,'igraph_modularity':q2,'connected_communities':k,'cluster_sizes':sizes[order].tolist(),'largest_fraction_active':float(sizes.max()/len(active)),'seconds':round(time.monotonic()-t,2),'assignment_sha256':hashlib.sha256(y.tobytes()).hexdigest()};results.append(rec);labels.append(y);print(name,gamma,seed,'communities',k,'Q',q,'largest',sizes.max(),'seconds',rec['seconds'],flush=True)
    aa=labels[1][active];bb=labels[3][active];ari=float(adjusted_rand_score(aa,bb));out=directory/f'{name}_assignments.private.jsonl.gz'
    with out.open('wb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as f:
        for i,aid in enumerate(ids):
            row={'article_id':aid,'node_index':i,'community':[None if y[i]<0 else int(y[i]) for y in labels]};f.write((json.dumps(row,separators=(',',':'))+'\n').encode())
    # Independent serialized replay against sizes, nulls, identity, and assignment hashes.
    counters=[Counter() for _ in labels];replay=np.full((len(labels),N),-1,np.int32)
    with gzip.open(out,'rt') as f:
        count=0
        for i,line in enumerate(f):
            r=json.loads(line);assert r['node_index']==i and r['article_id']==ids[i] and len(r['community'])==len(labels);count+=1
            for j,c in enumerate(r['community']):
                counters[j][c]+=1
                if c is not None:replay[j,i]=c
    assert count==N
    for j,r in enumerate(results):
        assert counters[j][None]==r['structural_missing'] and sorted([n for k,n in counters[j].items() if k is not None],reverse=True)==r['cluster_sizes'];assert hashlib.sha256(replay[j].tobytes()).hexdigest()==r['assignment_sha256']
    assert abs(adjusted_rand_score(replay[1,active],replay[3,active])-ari)<1e-12
    report={'schema':'stage3-leiden-exploratory/v1','graph':name,'preflight':m,'source_sha256':pre['source_sha256'],'mapping_sha256':pre['mapping_sha256'],'algorithm':'igraph community_leiden','igraph_version':ig.__version__,'objective':'weighted modularity','beta':.01,'runs':results,'seed_ari_active_gamma1':ari,'assignments_file':out.name,'assignments_sha256':sha(out),'checks':'exact frozen graph SHA / PAC1 re-encoding; igraph active identity/strength/sample weight; independent modularity and induced connectivity; full serialized ID/count/hash/ARI replay PASS','scope':'exploratory within-graph parameter sensitivity; no scientific validation or cross-lens ranking'}
    (directory/f'{name}_report.private.json').write_text(json.dumps(report,indent=2,allow_nan=False));print(name,'DONE ARI',ari,'sha',sha(directory/f'{name}_report.private.json'),flush=True)
if __name__=='__main__':run(Path(sys.argv[1]),sys.argv[2])

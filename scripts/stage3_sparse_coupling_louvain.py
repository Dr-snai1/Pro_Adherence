#!/usr/bin/env python3
"""Source-free sparse multilevel Louvain diagnostic for full frozen PAC1 coupling graph.

Respects weighted unordered pairs and isolates. Not Leiden and not accepted
scientific theme identification. Uses exact gamma modularity. Original data
and assignments remain private. Independent modularity cross-checks required.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,os,platform,struct,time,zlib
from collections import Counter
from pathlib import Path
import numpy as np
from scipy import sparse
from numba import njit
from sklearn.metrics import adjusted_rand_score,normalized_mutual_info_score

N=57204
SHA='bf7502ac23eaed295025e59155c2e6ea2e96df09542239051e0eddd88f548f46'
PAIR_COUNT=15871086;INCIDENCES=18490159
@njit(cache=True)
def parse_varint(b,p):
    result=0;shift=0
    while True:
        v=int(b[p]);p+=1;result|=(v&127)<<shift
        if v<128:break
        shift+=7
    return result,p
@njit(cache=True)
def decode_bytes(b,n,pairs):
    u=np.empty(pairs,np.int32);v=np.empty(pairs,np.int32);w=np.empty(pairs,np.int32)
    off=16;last=-1;sumw=0
    for i in range(pairs):
        d,off=parse_varint(b,off);val,off=parse_varint(b,off)
        last+=d
        uu=last//n;vv=last%n
        if not (d>0 and val>0 and uu<vv and vv<n):raise ValueError('Invalid PAC1 link')
        u[i]=uu;v[i]=vv;w[i]=val;sumw+=val
    if off!=len(b):raise ValueError('PAC1 trailing bytes')
    return u,v,w,sumw

@njit(cache=True)
def local_sweep(indptr,indices,weights,labels,totals,kvals,m2,gamma,order):
    n=len(labels)
    seen=np.zeros(n,np.int32)
    accum=np.zeros(n,np.float64)
    touched=np.empty(n,np.int32)
    stamp=0;changes=0
    for p in range(len(order)):
        node=int(order[p]);own=int(labels[node]);deg=kvals[node]
        if deg<=0:continue
        totals[own]-=deg;stamp+=1;size=0
        for k in range(indptr[node],indptr[node+1]):
            neighbor=int(indices[k]);
            if neighbor==node:continue  # aggregate self-loops never cause move
            c=int(labels[neighbor])
            if seen[c]!=stamp:
                seen[c]=stamp;accum[c]=0.0;touched[size]=c;size+=1
            accum[c]+=weights[k]
        initial=accum[own] if seen[own]==stamp else 0.0
        best=own;score=initial-gamma*deg*totals[own]/m2
        for ix in range(size):
            dest=int(touched[ix]);val=accum[dest]-gamma*deg*totals[dest]/m2
            if val>score+1e-12:
                score=val;best=dest
        totals[best]+=deg
        if best!=own:labels[node]=best;changes+=1
    return changes

@njit(cache=True)
def modularity_raw(indptr,indices,weights,membership,gamma):
    n=len(membership)
    degree=np.empty(n,np.float64)
    total=0.0;internal=0.0
    for i in range(n):
        s=0.0
        for k in range(indptr[i],indptr[i+1]):
            w=float(weights[k]);s+=w
            if membership[i]==membership[indices[k]]:internal+=w
        degree[i]=s;total+=s
    totals=np.zeros(n,np.float64)
    for i in range(n):totals[membership[i]]+=degree[i]
    expected=0.0
    for x in totals:expected+=(x/total)**2
    return internal/total-gamma*expected,internal,total

def make_matrix(binary):
    data=Path(binary).read_bytes()
    if len(data)!=33095318 or hashlib.sha256(data).hexdigest()!=SHA or format(zlib.crc32(data)&0xffffffff,'08x')!='2b35a454':raise ValueError('PAC1 original hash/CRC mismatch')
    if data[:4]!=b'PAC1':raise ValueError('header')
    n,num,weights=struct.unpack_from('<III',data,4)
    if (n,num,weights)!=(N,PAIR_COUNT,INCIDENCES):raise ValueError('PAC1 corpus census mismatch')
    v=np.frombuffer(data,dtype=np.uint8)
    u,w,wt,wtotal=decode_bytes(v,N,PAIR_COUNT)
    if wtotal!=INCIDENCES:raise ValueError('Weight total mismatch')
    active=np.zeros(N,dtype=bool);active[u]=True;active[w]=True
    rows=np.concatenate((u,w));cols=np.concatenate((w,u));val=np.concatenate((wt,wt))
    mat=sparse.coo_matrix((val,(rows,cols)),shape=(N,N)).tocsr()
    assert mat.nnz==PAIR_COUNT*2 and np.all(mat.diagonal()==0)
    assert np.array_equal(mat.indptr.astype(np.int64)[-1:],np.array([PAIR_COUNT*2]))
    assert int(mat.data.sum())==2*INCIDENCES and np.array_equal(mat.indices,mat.indices) # integer weights
    return mat,active

def run_one(mat,active,gamma,seed):
    n=mat.shape[0];labels_global=np.arange(n,dtype=np.int32)
    baseline=0.0;levels=[];mat_level=mat
    t0=time.perf_counter()
    for level in range(12):
        size=mat_level.shape[0]
        degree=np.asarray(mat_level.sum(axis=1)).ravel().astype(np.float64)
        m2=float(degree.sum())
        assign=np.arange(size,dtype=np.int32)
        totals=degree.copy()
        rng=np.random.default_rng(seed+level*9176)
        sweeps=[]
        for sweep in range(12):
            order=rng.permutation(size).astype(np.int32)
            changes=int(local_sweep(mat_level.indptr,mat_level.indices,mat_level.data,assign,totals,degree,m2,gamma,order))
            sweeps.append(changes)
            if changes==0 or changes<max(1,int(size*0.0002)):break
        _, local=np.unique(assign,return_inverse=True)
        local=local.astype(np.int32)
        assert local.shape==(size,)
        if level==0:labels_global=local.copy()
        else:labels_global=local[labels_global]
        Q,internal,total=modularity_raw(mat.indptr,mat.indices,mat.data,labels_global,gamma)
        if Q+1e-10<baseline:raise AssertionError(f'Modularity decreased at level {level}: {Q} < {baseline}')
        baseline=Q
        levels.append({'level':level,'input_supernodes':size,'new_supernodes':int(local.max()+1),'moves_per_sweep':sweeps,'modularity_original':float(Q)})
        print(json.dumps({'level':level,'gamma':gamma,'seed':seed,'nodes':size,'communities':int(local.max()+1),'Q':float(Q),'sweeps':sweeps}),flush=True)
        if local.max()+1==size or level>=11:break
        k=int(local.max()+1)
        onehot=sparse.csr_matrix((np.ones(size,dtype=np.int8),(np.arange(size),local)),shape=(size,k))
        next_mat=(onehot.T @ mat_level @ onehot).tocsr()
        assert int(next_mat.data.sum())==int(mat_level.data.sum()),'Graph weight not preserved during aggregation'
        mat_level=next_mat
    # remove structural isolates instead of assigning them singleton discoveries
    distinct,canon=np.unique(labels_global[active],return_inverse=True)
    sizes=np.bincount(canon,minlength=len(distinct))
    order=sorted(range(len(distinct)),key=lambda c:(-sizes[c],int(np.min(np.flatnonzero(canon==c)))))
    rename=np.empty(len(distinct),dtype=np.int32)
    for new,old in enumerate(order):rename[old]=new
    out=np.full(n,-1,dtype=np.int32);out[active]=rename[canon]
    q,internal,total=modularity_raw(mat.indptr,mat.indices,mat.data,labels_global,gamma)
    # fully independent vectorized modularity calculation in original graph
    strength=np.asarray(mat.sum(axis=1)).ravel().astype(np.float64)
    totals=np.bincount(labels_global,weights=strength,minlength=len(labels_global))
    expected=float(gamma*np.sum(np.square(totals/totals.sum())))
    inside_float=0.0
    for a in range(n):
        start,end=mat.indptr[a],mat.indptr[a+1]
        inside_float+=np.sum(mat.data[start:end][labels_global[mat.indices[start:end]]==labels_global[a]],dtype=np.float64)
    independent=float(inside_float/strength.sum()-expected)
    assert abs(q-independent)<1e-9,(q,independent)
    info={'gamma':gamma,'seed':seed,'active_nodes':int(sum(active)),'missing_structural':int(sum(~active)),
          'communities':len(distinct),'top_cluster_sizes':sorted(map(int,sizes),reverse=True)[:30],
          'modularity':q,'independent_modularity':independent,
          'internal_weight_oriented':float(internal),'total_weight_oriented':float(total),
          'levels':levels,'runtime_seconds':round(time.perf_counter()-t0,2)}
    return out,info

def main(input_path,private_dir):
    os.environ.setdefault('NUMBA_NUM_THREADS','1')
    private_dir.mkdir(parents=True,exist_ok=False,mode=0o700)
    mat,active=make_matrix(input_path)
    print(json.dumps({'phase':'verified_input','edges':mat.nnz//2,'active':int(active.sum()),'isolates':int((~active).sum()),'weight':int(mat.data.sum()//2)}),flush=True)
    configs=[(0.75,20261031),(1.0,20261031),(1.25,20261031),(1.0,20261032)]
    memberships=[];reports=[]
    for gamma,seed in configs:
        labels,info=run_one(mat,active,gamma,seed);memberships.append(labels);reports.append(info)
        print(json.dumps({'phase':'run_complete','gamma':gamma,'seed':seed,'Q':info['modularity'],'n_clusters':info['communities']}),flush=True)
    stability=[]
    for i in range(4):
        for j in range(i+1,4):
            r={'left':i,'right':j,'ari':float(adjusted_rand_score(memberships[i][active],memberships[j][active])),
               'nmi':float(normalized_mutual_info_score(memberships[i][active],memberships[j][active]))}
            stability.append(r)
    # article ID mapping from original frozen immutable node roster read separately by caller
    assignments=private_dir/'coupling_louvain_membership_indices.private.jsonl.gz'
    with open(assignments,'xb') as f,gzip.GzipFile(fileobj=f,filename='',mode='wb',mtime=0,compresslevel=6) as z:
        for idx in range(N):
            z.write((json.dumps({'node_index':idx,'communities':[int(v[idx]) if v[idx]>=0 else None for v in memberships]},separators=(',',':'))+'\n').encode())
    count=0
    with gzip.open(assignments,'rt') as f:
        for line in f:
            obj=json.loads(line);assert obj['node_index']==count;count+=1
    assert count==N
    summary={'schema':'stage3-full-bibliographic-coupling-sparse-louvain/v1','algorithm':'sparse multilevel Louvain numba/scipy','scientific_accepted':False,
             'pruning':None,'weight_semantics':'original weighted PAC1; complete graph','input_sha256':SHA,
             'full_edges':PAIR_COUNT,'weighted_incidences':INCIDENCES,'runs':reports,'stability':stability,
             'warnings':['Exploratory custom sparse implementation, validated by independent modularity','Not Leiden','Missing citation coverage not zero','Do not interpret community IDs as scientific topic labels']}
    summary_path=private_dir/'coupling_louvain_summary.private.json';summary_path.write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n')
    def h(p):
        with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
    manifest={'status':'LOCAL_NEEDS_REMOTE_READBACK','schema':'stage3-private-coupling-community/v1',
              'code_sha256':h(__file__),'input_sha256':SHA,'outputs':{p.name:{'sha256':h(p),'bytes':p.stat().st_size} for p in (assignments,summary_path)},
              'python':platform.python_version()}
    (private_dir/'coupling_louvain_manifest.private.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'phase':'complete','manifest':manifest,'headline':[{'gamma':a['gamma'],'seed':a['seed'],'comm':a['communities'],'Q':a['modularity']} for a in reports]}),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--pac1',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args();main(args.pac1,args.out)

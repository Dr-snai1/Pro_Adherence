#!/usr/bin/env python3
"""Label frozen node2vec HDBSCAN partitions, reusing semantic title-only TF-IDF rules."""
import gzip, hashlib, json, math, re, zipfile, sys
from pathlib import Path
from collections import Counter
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import adjusted_rand_score
root=Path(sys.argv[1]); out=Path(sys.argv[2]);
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
accept=root/'STAGE3_20261115_PRIVATE_NODE2VEC_HDBSCAN_ACCEPTANCE.json'; assignment=root/'STAGE3_20261115_PRIVATE_node2vec_hdbscan_assignments.private.jsonl.gz'; roster=root/'STAGE3_20261115_PRIVATE_PUBMEDBERT_HDBSCAN_roster.jsonl.gz'; source=root/'STAGE3_20261112_PRIVATE_FULL_PUBMEDBERT_INPUTS.zip'; cat=root/'STAGE3_20261127_PRIVATE_CLUSTER_LABELS_TFIDF.json'
assert sha(accept)=='65ac24489e0a70541f3c8166e727f2039332be31fc673145c035723d766c84ff'; assert sha(assignment)=='f5043d0757445041e2610eae5357116998cc4dc8700e6e5fe56f3904a4d72cea'; assert sha(cat)=='a95a386da0afb07e57235624b4a84a4f3a58b2db0ca865d2ba0a86d84d87256a'
a=json.loads(accept.read_text()); c=json.loads(cat.read_text()); N=c['n'];assert sha(roster)==c['roster_sha256'] and sha(source)==c['source_sha256']; R=[json.loads(l) for l in gzip.open(roster,'rt')]; A=[json.loads(l) for l in gzip.open(assignment,'rt')];assert len(R)==len(A)==N and len({r['article_id'] for r in R})==N and all(r['article_id']==x['article_id'] and x['node_index']==i for i,(r,x) in enumerate(zip(R,A)))
titles=[]; only=[]
with zipfile.ZipFile(source) as z:
    assert z.testzip() is None
    with gzip.GzipFile(fileobj=z.open('full_pubmedbert_inputs.private.jsonl.gz')) as f:
        for i,l in enumerate(f):
            r=json.loads(l);assert (r['article_id'],r['text_state'])==(R[i]['article_id'],R[i]['text_state']); titles.append(r['title'] or ''); only.append(r['text_state']=='title_only')
assert len(titles)==N;only=np.array(only);stop=set(c['stop_words'])
def analyzer(text):
    tok=re.findall(r'\b[a-zA-Z][a-zA-Z0-9]+\b',text.lower()); keep=[t not in stop for t in tok]
    return [t for t,k in zip(tok,keep) if k]+[tok[i]+' '+tok[i+1] for i in range(len(tok)-1) if keep[i] and keep[i+1]]
v=TfidfVectorizer(analyzer=analyzer,min_df=3,max_df=.65,max_features=35000,sublinear_tf=True,dtype=np.float32);X=v.fit_transform(titles).tocsr(); terms=v.get_feature_names_out();assert len(terms)==c['vocabulary'] and int(sum(np.diff(X.indptr)>0))==c['nonempty_tfidf_rows'];B=X.copy();B.data[:]=1;gdf=np.asarray(B.sum(axis=0)).ravel();
ready=np.array([x['vector_status']=='ready' for x in A]);assert sum(ready)==a['ready_unit_vectors']; assert N-sum(ready)==a['missing_structural'];parts=[];lab={}
for run in a['method']['runs']:
    mcs=run['min_cluster_size']; rs=[next(r for r in x['results'] if r['min_cluster_size']==mcs) if x['results'] is not None else {'cluster':None,'is_noise':False} for x in A]; y=np.array([(-2 if not ready[i] else -1) if r['cluster'] is None else r['cluster'] for i,r in enumerate(rs)],dtype=np.int32);lab[mcs]=y;assert np.array_equal(y==-2,~ready);assert all(bool(r['is_noise'])==(y[i]==-1) for i,r in enumerate(rs));ids,sz=np.unique(y[y>=0],return_counts=True);assert len(ids)==run['clusters'] and int(sz.sum())==run['assigned'] and int((y==-1).sum())==run['noise'] and sorted(sz.tolist(),reverse=True)[:len(run['largest_clusters'])]==run['largest_clusters'];
    row=np.flatnonzero(y>=0); grp=np.searchsorted(ids,y[row]);G=csr_matrix((np.ones(len(row),np.float32),(grp,row)),shape=(len(ids),N));S=(G@X).tocsr();F=(G@B).tocsr();S.sort_indices();F.sort_indices();assert np.array_equal(S.indices,F.indices) and np.array_equal(S.indptr,F.indptr) and np.array_equal(np.asarray(G.sum(axis=1)).ravel().astype(int),sz);oc=np.bincount(grp,weights=only[row],minlength=len(ids)).astype(int); records=[]
    for j,(cid,n) in enumerate(zip(ids,sz)):
        s=slice(S.indptr[j],S.indptr[j+1]);ix=S.indices[s];freq=F.data[s];share=freq/n;lift=share/(gdf[ix]/N);score=S.data[s]/n*np.log1p(lift);eligible=np.flatnonzero((freq>=max(2,math.ceil(.03*n)))&(lift>1));fallback=not len(eligible)
        if fallback:eligible=np.flatnonzero(freq>=2)
        order=sorted(eligible,key=lambda t:(-float(score[t]),str(terms[ix[t]])))[:30];chosen=[];used=set()
        for t in order:
            words=set(terms[ix[t]].split())
            if words&used:continue
            chosen.append(t);used|=words
            if len(chosen)==2:break
        name=' / '.join(str(terms[ix[t]]) for t in chosen) or 'Unclear topic'; first=float(share[order[0]]) if order else 0.; flags=[]
        if n/N>=.2:flags.append('large >=20% of corpus')
        if first<.1 or fallback:flags.append('weak term support')
        if oc[j]/n>=.8:flags.append('>=80% title-only')
        records.append(dict(cluster_id=int(cid),n=int(n),label=name,keywords=[dict(term=str(terms[ix[t]]),support=float(share[t]),lift=float(lift[t])) for t in order[:8]],title_only=int(oc[j]),flags=flags))
    records.sort(key=lambda r:(-r['n'],r['cluster_id'])); cnt=Counter(int(t) for t in y);assert len({r['cluster_id'] for r in records})==len(ids) and all(cnt[r['cluster_id']]==r['n'] for r in records) and sum(r['n'] for r in records)+cnt[-1]+cnt[-2]==N
    parts.append(dict(mcs=mcs,ms=10,dimension=128,noise=cnt[-1],structural_missing=cnt[-2],assigned=int(sz.sum()),clusters=records,noise_fraction_ready=cnt[-1]/int(sum(ready)),largest_fraction_assigned=records[0]['n']/int(sz.sum())))
for r in a['method']['sensitivity']:
    x=lab[r['min_cluster_size_A']][ready];y=lab[r['min_cluster_size_B']][ready];both=(x>=0)&(y>=0);assert int(both.sum())==r['both_assigned_rows'] and abs(adjusted_rand_score(x,y)-r['ari_including_noise_as_label'])<1e-12 and abs(adjusted_rand_score(x[both],y[both])-r['ari_jointly_assigned'])<1e-12
obj=dict(schema='stage3-node2vec-title-catalog/v1',scope='exploratory automatic cluster labels; no refit; no cross-view ranking or scientific validation',n=N,ready=int(sum(ready)),missing_structural=int(N-sum(ready)),method=c['method'],source_sha256=sha(source),roster_sha256=sha(roster),assignment_sha256=sha(assignment),acceptance_sha256=sha(accept),semantic_catalog_sha256=sha(cat),vocabulary=len(terms),partitions=parts,sensitivity=a['method']['sensitivity'],verification='SHA and roster identity; counts checked vs frozen acceptance; independent Counter, and ARI replay PASS')
out.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False,indent=2));out.chmod(0o600)
print('SHA',sha(out));print('CODE SHA',sha(Path(__file__)))
for p in parts:print(p['mcs'],len(p['clusters']),p['noise_fraction_ready'],p['largest_fraction_assigned'], '; '.join(f"{r['label']} ({r['n']})" for r in p['clusters']))

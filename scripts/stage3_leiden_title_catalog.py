"""Label every stored Leiden community with the frozen title-only TF-IDF rules.
Small components and unclear terms are retained, not converted to HDBSCAN noise.
"""
import sys, gzip, json, hashlib, math, re, zipfile
from pathlib import Path
from collections import Counter
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from stage3_leiden_graphs import sha, N, EXPECTED

NAMES={'direct':'Direct citation (undirected, binary)','cocitation':'Co-citation (weighted)','coupling':'Bibliographic coupling (weighted)'}
def main(root,directory,out):
    cp=root/'STAGE3_20261127_PRIVATE_CLUSTER_LABELS_TFIDF.json';assert sha(cp)=='a95a386da0afb07e57235624b4a84a4f3a58b2db0ca865d2ba0a86d84d87256a';cat=json.loads(cp.read_text());sp=root/'STAGE3_20261112_PRIVATE_FULL_PUBMEDBERT_INPUTS.zip';rp=root/'STAGE3_20261115_PRIVATE_PUBMEDBERT_HDBSCAN_roster.jsonl.gz';assert sha(sp)==cat['source_sha256'] and sha(rp)==cat['roster_sha256'];R=[json.loads(l) for l in gzip.open(rp,'rt')];assert len(R)==N and len({r['article_id'] for r in R})==N
    pre=json.loads((directory/'graph_preflight.json').read_text());mp=directory/'mapping.json';assert sha(mp)==pre['mapping_sha256'];ids=json.loads(mp.read_text());assert len(ids)==N and set(ids)=={r['article_id'] for r in R};index={r['article_id']:i for i,r in enumerate(R)};perm=np.array([index[a] for a in ids],np.int32);assert len(np.unique(perm))==N
    titles=[];only=[]
    with zipfile.ZipFile(sp) as z:
        assert z.testzip() is None
        with gzip.GzipFile(fileobj=z.open('full_pubmedbert_inputs.private.jsonl.gz')) as f:
            for i,l in enumerate(f):
                r=json.loads(l);assert (r['article_id'],r['text_state'])==(R[i]['article_id'],R[i]['text_state']);titles.append(r['title'] or '');only.append(r['text_state']=='title_only')
    assert len(titles)==N;only=np.asarray(only,dtype=bool)[perm];stop=set(cat['stop_words'])
    def analyzer(text):
        tok=re.findall(r'\b[a-zA-Z][a-zA-Z0-9]+\b',text.lower());keep=[t not in stop for t in tok];return [t for t,k in zip(tok,keep) if k]+[tok[i]+' '+tok[i+1] for i in range(len(tok)-1) if keep[i] and keep[i+1]]
    v=TfidfVectorizer(analyzer=analyzer,min_df=3,max_df=.65,max_features=35000,sublinear_tf=True,dtype=np.float32);X=v.fit_transform(titles).tocsr();terms=v.get_feature_names_out();assert len(terms)==cat['vocabulary'] and int(sum(np.diff(X.indptr)>0))==cat['nonempty_tfidf_rows'];X=X[perm].tocsr();B=X.copy();B.data[:]=1;gdf=np.asarray(B.sum(axis=0)).ravel();parts=[];reports={}
    for name in EXPECTED:
        f=directory/f'{name}_report.private.json';r=json.loads(f.read_text());a=directory/r['assignments_file'];assert sha(a)==r['assignments_sha256'];reports[name]={'report_sha256':sha(f),'assignment_sha256':sha(a),'seed_ari_active_gamma1':r['seed_ari_active_gamma1']};A=[json.loads(l) for l in gzip.open(a,'rt')];assert len(A)==N and all(x['article_id']==a and x['node_index']==i for i,(x,a) in enumerate(zip(A,ids)))
        for j,run in enumerate(r['runs']):
            y=np.array([-1 if x['community'][j] is None else x['community'][j] for x in A],np.int32);assert hashlib.sha256(y.tobytes()).hexdigest()==run['assignment_sha256'];row=np.flatnonzero(y>=0);grp=y[row];K=run['clusters'];sz=np.bincount(grp,minlength=K);assert len(row)==run['active'] and sz.tolist()==run['cluster_sizes'] and int((y<0).sum())==run['structural_missing']
            G=csr_matrix((np.ones(len(row),np.float32),(grp,row)),shape=(K,N));S=(G@X).tocsr();F=(G@B).tocsr();S.sort_indices();F.sort_indices();assert np.array_equal(S.indices,F.indices) and np.array_equal(S.indptr,F.indptr) and np.array_equal(np.asarray(G.sum(axis=1)).ravel().astype(int),sz);oc=np.bincount(grp,weights=only[row],minlength=K).astype(int);recs=[]
            for cid,n0 in enumerate(sz):
                n=int(n0);s=slice(S.indptr[cid],S.indptr[cid+1]);ix=S.indices[s];freq=F.data[s];share=freq/n;lift=share/(gdf[ix]/N);score=S.data[s]/n*np.log1p(lift);elig=np.flatnonzero((freq>=max(2,math.ceil(.03*n)))&(lift>1));fallback=not len(elig)
                if fallback:elig=np.flatnonzero(freq>=2)
                order=sorted(elig,key=lambda t:(-float(score[t]),str(terms[ix[t]])))[:30];chosen=[];used=set()
                for t in order:
                    words=set(terms[ix[t]].split())
                    if words&used:continue
                    chosen.append(t);used|=words
                    if len(chosen)==2:break
                name_label=' / '.join(str(terms[ix[t]]) for t in chosen) or 'Unclear topic';flags=[]
                if n<30:flags.append('small community <30')
                if n/N>=.2:flags.append('large >=20% of corpus')
                if not order or float(share[order[0]])<.1 or fallback:flags.append('weak term support')
                if oc[cid]/n>=.8:flags.append('>=80% title-only')
                recs.append({'cluster_id':cid,'n':n,'label':name_label,'keywords':[{'term':str(terms[ix[t]]),'support':float(share[t]),'lift':float(lift[t])} for t in order[:8]],'title_only':int(oc[cid]),'flags':flags})
            cnt=Counter(int(t) for t in y);assert len(recs)==K and all(cnt[x['cluster_id']]==x['n'] for x in recs) and sum(x['n'] for x in recs)==run['active']
            counts={f'communities_lt{limit}':sum(x['n']<limit for x in recs) for limit in [5,10,30,80,150]};counts['articles_in_communities_lt30']=sum(x['n'] for x in recs if x['n']<30);counts['unclear_labels']=sum(x['label']=='Unclear topic' for x in recs)
            parts.append({'graph':name,'graph_label':NAMES[name],'resolution':run['resolution'],'seed':run['seed'],'active':run['active'],'structural_missing':run['structural_missing'],'cluster_count':K,'largest_fraction_active':run['largest_fraction_active'],'modularity':run['modularity'],'counts':counts,'clusters':recs});print(name,run['resolution'],run['seed'],K,counts,'top',[(x['label'],x['n']) for x in recs[:5]],flush=True)
    assert len(parts)==12
    o={'schema':'stage3-leiden-title-catalog/v1','scope':'all exploratory Leiden communities; title-only automatic provisional annotations; no refit; no cross-method ranking or scientific validation; graph isolates are structural null, no HDBSCAN noise','n':N,'source_sha256':sha(sp),'roster_sha256':sha(rp),'semantic_catalog_sha256':sha(cp),'mapping_sha256':sha(mp),'method':cat['method'],'vocabulary':len(terms),'reports':reports,'partition_count':len(parts),'cluster_occurrences':sum(p['cluster_count'] for p in parts),'partitions':parts,'verification':'all source/roster/assignment hashes and identity align; independent counts and size replay PASS'}
    out.write_text(json.dumps(o,ensure_ascii=False,allow_nan=False,indent=2));out.chmod(0o600)
    tsv=out.with_suffix('.tsv')
    with tsv.open('w',encoding='utf-8-sig') as f:
        f.write('Сетка\tРазбиение\tВсе имена кластеров (ID: метка (n))\n')
        for p in parts:
            config=f"Leiden modularity; gamma={p['resolution']}; seed={p['seed']}; beta=0.01; n_iterations=-1; communities={p['cluster_count']}; structural missing={p['structural_missing']}/{N}; Q={p['modularity']:.6f}"
            names='; '.join(f"{x['cluster_id']}: {x['label']} ({x['n']})" for x in p['clusters']);f.write(f"{p['graph_label']}\t{config}\t{names}\n")
    tsv.chmod(0o600);print('DONE',o['cluster_occurrences'],sha(out),sha(tsv),flush=True)
if __name__=='__main__':main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
